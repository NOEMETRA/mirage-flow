
import numpy as np
from typing import List, Tuple, Optional
from .core import PacketFlow, MirageConfig, pn_key

class PairwiseDelayEmbedder:
    """
    Injects watermark into traffic flows using Pairwise Packet Delays.
    Based on Nexus-Flow v3.7 logic.
    """
    def __init__(self, config: MirageConfig, key: np.ndarray):
        self.a = float(config.ROBUST_A)
        self.key = key.astype(np.int8)
        self.blk_size = config.BLOCK_SIZE
        self.repeats = config.REPEATS
        self.gap = config.GAP_CHIPS

    def embed(self, flow: PacketFlow, start_idx: int) -> Tuple[PacketFlow, int]:
        """
        Embeds the robust watermark pattern repeats.
        Returns: (MarkedFlow, NumRepeatsEmbedded)
        """
        ts = flow.ts.copy()
        out_ts = ts.copy()
        
        # Calculate structure
        key_len = len(self.key)
        gap_packets = 2 * self.gap
        
        # Embed loop
        p = start_idx
        embedded_count = 0
        
        for _ in range(self.repeats):
            # Check bounds (Need 2*N + 1 packets)
            if p + 2*key_len + 1 >= len(out_ts):
                break
                
            # Apply pairwise shifts
            add = np.zeros_like(out_ts) # Temporary shift buffer
            local_p = p
            for c in self.key:
                if c == 1:
                    add[local_p] += self.a
                else:
                    add[local_p+1] += self.a
                local_p += 2
            
            # Apply shifts cumulatively to preserve monotonicity locally
            # Note: In full implementation we need careful monotonicity.
            # Here we apply the shifts to the base timeline and re-sort/accumulate
            # effectively.
            
            # Simplified approach matching v3.7 verified script:
            # We add the delay to the specific packets.
            out_ts += add
            
            # Advance ptr
            p += 2*key_len + gap_packets
            embedded_count += 1
            
        # Enforce monotonicity global
        out_ts = np.maximum.accumulate(out_ts)
        # Normalize start
        out_ts = out_ts - out_ts[0]
        
        return PacketFlow(out_ts, flow.sizes), embedded_count

class FlowDetector:
    """
    Stateful detector using Robust Top-K Fusion (v3.7).
    """
    def __init__(self, config: MirageConfig, key: np.ndarray):
        self.config = config
        self.key = key
        self.history_ts = []
        
        # Pre-compute metrics constants
        self.spacing = config.BLOCK_SIZE + config.GAP_CHIPS
        
    def ingest(self, new_timestamps: List[float]):
        """Feed new packet arrival times into the buffer."""
        self.history_ts.extend(new_timestamps)
        
        # Prune old history to keep memory minimal
        # Keep enough for 2x WINDOW_SIZE just in case
        cutoff = new_timestamps[-1] - (self.config.WINDOW_SIZE * 2)
        if len(self.history_ts) > 0 and self.history_ts[0] < cutoff:
            # Efficient list slicing for simple buffer
            # Find index to cut
            cut_idx = 0
            for i, t in enumerate(self.history_ts):
                if t >= cutoff:
                    cut_idx = i
                    break
            self.history_ts = self.history_ts[cut_idx:]

    def analyze(self, current_time: float) -> float:
        """
        Runs the detection algorithm on the window [now - WINDOW, now].
        Returns: Z-Score (Attribution Confidence)
        """
        cutoff = current_time - self.config.WINDOW_SIZE
        
        # Filter window
        valid_ts = np.array([t for t in self.history_ts if t > cutoff])
        
        # Min packets check
        if len(valid_ts) < 100:
            return 0.0
            
        flow = PacketFlow(valid_ts)
        iats = flow.iats
        
        if len(iats) < len(self.key):
            return 0.0

        # 1. Compute Correlation Traces (Phase 0 and Phase 1)
        c0 = self._sliding_corr_trace(self._pairwise_obs(iats, 0))
        c1 = self._sliding_corr_trace(self._pairwise_obs(iats, 1))
        
        # 2. Score (Raw Top-K)
        # Dynamic K adaptation for Sliding Window:
        # We must only sum peaks that can physically exist in the current window.
        # Packets in window (approx) can vary, but we know the time duration.
        # Repeat Duration (s) = (2*Block + 2*Gap) * BaseIAT
        # But we don't know BaseIAT perfectly (jitter).
        # We can estimate Repeats via Packet Count.
        
        # Packets available
        n_pkts = len(valid_ts)
        # Packets per repeat structure (2*Key + 2*Gap)
        # Note: Gap is config.GAP_CHIPS, but embedder uses 2*GAP_CHIPS packets.
        # Key is BLOCK_SIZE, embedder uses 2*BLOCK_SIZE packets (pairwise).
        # Total packets per repeat = 2*512 + 2*32 = 1088.
        structure_len = 2*self.config.BLOCK_SIZE + 2*self.config.GAP_CHIPS
        
        expected_repeats = max(1, n_pkts // structure_len)
        
        # Use the heuristic K
        K = expected_repeats
        
        s0 = self._score_topk(c0, K, self.spacing)
        s1 = self._score_topk(c1, K, self.spacing)
        raw_score = max(s0, s1)
        
        # 3. Normalize (Z-Score) via Empirical Background Estimation
        # (Restored from v3.7 verified logic)
        score_fn = lambda c_trace: self._score_topk(c_trace, K, self.spacing)
        
        # Real Score
        real_s = max(s0, s1)
        
        # Background Stats (Wrong Keys)
        # We generate random keys and compute their scores on the SAME flow.
        # This accounts for flow texture (jitter) and K size automatically.
        bg_scores = []
        # Optimization: Use fewer keys for realtime (e.g. 20)
        n_wrong = 20 
        
        for _ in range(n_wrong):
            wk = pn_key(len(self.key))
            wc0 = self._sliding_corr_trace(self._pairwise_obs(iats, 0), key_override=wk)
            wc1 = self._sliding_corr_trace(self._pairwise_obs(iats, 1), key_override=wk)
            bg_scores.append(max(score_fn(wc0), score_fn(wc1)))
            
        bg_mean = float(np.mean(bg_scores))
        bg_std = float(np.std(bg_scores) + 1e-10)
        
        z = (real_s - bg_mean) / bg_std
        return z

    def _pairwise_obs(self, iats: np.ndarray, phase: int) -> np.ndarray:
        start = phase
        usable = len(iats) - start
        pairs = usable // 2
        if pairs <= 0: return np.array([])
        a = iats[start:start + 2*pairs:2]
        b = iats[start + 1:start + 2*pairs:2]
        return a - b

    def _sliding_corr_trace(self, vec: np.ndarray, key_override: Optional[np.ndarray] = None) -> np.ndarray:
        target_key = key_override if key_override is not None else self.key
        
        if len(vec) < len(target_key): return np.array([])
        # Standardize inputs
        v_std = vec.std() + 1e-10
        k_std = target_key.std() + 1e-10
        x = (vec - vec.mean()) / v_std
        k = (target_key - target_key.mean()) / k_std
        
        return np.correlate(x, k, mode="valid") / len(k)

    def _score_topk(self, c: np.ndarray, topk: int, min_sep: int) -> float:
        if c.size == 0: return 0.0
        v = np.abs(c).copy()
        s = 0.0
        for _ in range(topk):
            idx = np.argmax(v)
            s += float(v[idx])
            
            # Inhibition window
            lo = max(0, idx - min_sep//2)
            hi = min(len(v), idx + min_sep//2 + 1)
            v[lo:hi] = 0.0
            
            if v.max() <= 0:
                break
        return s

try:
    import scapy.all as scapy
    SCAPY_AVAILABLE = True
except ImportError:
    SCAPY_AVAILABLE = False

import collections
import threading

class TrafficTracker:
    def __init__(self, maxlen=5000):
        self.history = collections.deque(maxlen=maxlen) # (ts, src_ip)
        self.lock = threading.Lock()
        
    def add(self, ts: float, src_ip: str):
        with self.lock:
            self.history.append((ts, src_ip))
        
    def get_dominant_ip(self, duration: float, current_time: float) -> str:
        """Returns the most frequent source IP in the last `duration` seconds."""
        cutoff = current_time - duration
        
        with self.lock:
            # Safe iteration under lock
            ips = [ip for t, ip in self.history if t > cutoff]
        
        if not ips:
            return "Unknown"
            
        # Count
        counts = collections.Counter(ips)
        return counts.most_common(1)[0][0]

class LiveMonitor:
    """
    Captures live traffic using Scapy and feeds the FlowDetector.
    """
    def __init__(self, detector: FlowDetector, interface: Optional[str] = None):
        if not SCAPY_AVAILABLE:
            raise ImportError("Scapy not installed. Cannot run LiveMonitor.")
            
        self.detector = detector
        self.interface = interface
        self.running = False
        self.packet_count = 0
        self.tracker = TrafficTracker()
        
    def get_attributed_ip(self, duration: float = 30.0) -> str:
        # We use time.time() as reference since detector uses it
        import time
        return self.tracker.get_dominant_ip(duration, time.time())
        
    def start(self, async_mode: bool = True):
        import threading
        self.running = True
        print(f"[*] Starting Live Monitor on interface: {self.interface or 'DEFAULT'}")
        
        if async_mode:
            self.thread = threading.Thread(target=self._sniff_loop, daemon=True)
            self.thread.start()
        else:
            self._sniff_loop()
            
    def stop(self):
        self.running = False
        
    def _sniff_loop(self):
        # Filter: UDP traffic (VoIP / Tunneling) usually
        # For demo, we sniff ALL IP traffic to be safe
        try:
            scapy.sniff(
                iface=self.interface,
                prn=self._process_packet,
                store=False,
                stop_filter=lambda x: not self.running
            )
        except Exception as e:
            print(f"[!] Sniffing Error: {e}")
            self.running = False
            
    def _process_packet(self, pkt):
        if not self.running: return
        
        # Extract Timestamp
        # Scapy timestamps can be float enum
        ts = float(pkt.time)
        
        # Extract IP (Attribution)
        src_ip = "Unknown"
        if pkt.haslayer(scapy.IP):
            src_ip = pkt[scapy.IP].src
        
        # Feed Detector
        self.detector.ingest([ts])
        self.tracker.add(ts, src_ip)
        self.packet_count += 1

