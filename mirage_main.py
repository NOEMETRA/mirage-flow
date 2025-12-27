
import argparse
import time
import numpy as np
import matplotlib.pyplot as plt
from typing import List

from mirage.core import MirageConfig, PacketFlow, pn_key
from mirage.surveillance import FlowDetector, PairwiseDelayEmbedder
try:
    from mirage.surveillance import LiveMonitor
    LIVE_SUPPORT = True
except ImportError:
    LIVE_SUPPORT = False
    
from mirage.countermeasures import ActiveDefenseController

def run_live_monitor(interface: str, duration: float):
    if not LIVE_SUPPORT:
        print("[!] Error: Scapy not installed or LiveMonitor unavailable.")
        return

    print(f"--- MIRAGE System v4.1 (LIVE MONITOR) ---")
    print(f"Interface: {interface or 'Auto-Detect'}")
    
    # Setup
    config = MirageConfig()
    # Live requires a legitimate key. In real usage, this should be loaded from secure storage.
    key = pn_key(config.BLOCK_SIZE, seed=42) 
    
    detector = FlowDetector(config, key)
    monitor = LiveMonitor(detector, interface)
    defense = ActiveDefenseController(config)
    
    # Start Sniffing
    monitor.start(async_mode=True)
    
    print("System Armed. Listening for traffic...")
    print("Press Ctrl+C to stop.")
    
    try:
        t_start = time.time()
        
        while True:
            t_now = time.time()
            if duration > 0 and (t_now - t_start) > duration:
                break
                
            # Analysis Cycle (Every 1s)
            time.sleep(1.0)
            
            # Get Current Z (Detector buffer updates via Thread)
            z = detector.analyze(t_now) # We use wall clock time? 
            # Note: Scapy timestamps are absolute. FlowDetector expects same ref.
            # If scapy uses time.time(), we are good.
            
            # Defense Update
            dt = 1.0 
            effects = defense.update(z, dt)
            
            # Log
            state = "ENGAGED" if effects["engaged"] else "MONITORING"
            lat = effects["latency_penalty"] * 1000
            n_pkts = monitor.packet_count
            attacker = monitor.get_attributed_ip()
            reason = effects.get("reason", "")
            
            # Compact Log Line
            # [Time] Pkts | Z | Lat | State | Attacker | Reason
            ts_str = time.strftime('%H:%M:%S')
            if state == "ENGAGED":
                 print(f"[{ts_str}] Pkts:{n_pkts} | Z:{z:5.1f} | Lat:{lat:3.0f}ms | {state} | SRC:{attacker} | {reason}")
            else:
                 print(f"[{ts_str}] Pkts:{n_pkts} | Z:{z:5.1f} | Lat:{lat:3.0f}ms | {state}")
            
    except KeyboardInterrupt:
        print("\n[!] Stopping...")
    finally:
        monitor.stop()
        print("Monitor Stopped.")

def run_simulation(duration: float):
    print(f"--- MIRAGE System v4.1 (Integrated Simulation) ---")
    print(f"Duration: {duration}s")
    
    # 1. Setup
    config = MirageConfig()
    config.SIM_DURATION = duration
    
    # Secrets
    key = pn_key(config.BLOCK_SIZE, seed=42)
    
    # Components
    detector = FlowDetector(config, key)
    defense = ActiveDefenseController(config)
    embedder = PairwiseDelayEmbedder(config, key)
    
    # Simulation State
    t_now = 0.0
    dt_step = 0.05 # 50ms discrete steps
    
    # Metrics
    history_t = []
    history_z = []
    history_lat = []
    history_engaged = []
    
    # Attack Phase Control
    # Start Attack at 20% of duration
    attack_start = duration * 0.2
    
    # Initialize current_z for the loop
    current_z = 0.0
    
    
    # --- SIMULATION EXECUTION ---
    print("Generating Traffic Scenario...")
    
    # Baseline Flow
    n_packets = int(duration / 0.020)
    ts = np.arange(n_packets) * 0.020
    # Add Jitter (Source Jitter = 0.5ms, matching v3.7 verified config)
    ts += np.random.normal(0, 0.0005, size=n_packets)
    ts = np.sort(ts)
    
    flow_obj = PacketFlow(ts)
    
    # Inject Watermark after attack_start
    # Find index
    start_idx = np.searchsorted(ts, attack_start)
    
    # Embed
    marked_flow, n_emb = embedder.embed(flow_obj, start_idx=start_idx)
    final_ts = marked_flow.ts
    
    print(f"Traffic Generated. Embedded {n_emb} robust blocks starting at T={attack_start:.1f}s")
    
    # --- RUNTIME LOOP (Replay the Flow) ---
    print("Streaming packets to Detector...")
    
    # We iterate through the timestamps as if they are arriving
    # We maintain a virtual clock 't_sim'
    
    packet_idx = 0
    t_sim = 0.0
    
    while t_sim < duration and packet_idx < len(final_ts):
        # 1. Next Packet Arrival
        arrival_time = final_ts[packet_idx]
        
        # Advance simulation time
        dt = arrival_time - t_sim
        if dt < 0: dt = 0
        t_sim = arrival_time
        
        # 2. Defense Effect (Tarpit)
        # Calculate defense state based on PREVIOUS knowledge
        # (We run defense update periodically, e.g. every packet or every 1s)
        
        # Mocking real-time: The latency penalty implies the packet arrives LATER
        # But we already have fixed timestamps?
        # In a real proxy, we would DELAY the packet here.
        # For simulation metric, we just calculate what the delay WOULD be.
        
        # Run Defense Update Cycle (Optimized: Every 50 packets)
        if packet_idx % 50 == 0:
            current_z = detector.analyze(t_sim)
        # (Else keep previous Z)
        
        # Defense Controller Step (update internal timer)
        # We approximate dt for the controller as the packet IAT
        effects = defense.update(current_z, dt)
        
        added_latency = effects["latency_penalty"]
        
        # 3. Store Data
        if packet_idx % 50 == 0: # Log every 50 packets to save memory
            history_t.append(t_sim)
            history_z.append(current_z)
            history_engaged.append(1.0 if effects["engaged"] else 0.0)
            history_lat.append(added_latency * 1000)
            
        # 4. Ingest Packet into Detector
        # (Detector sees the packet AFTER network delay? 
        # Usually Detector is at the Gateway. Tarpit is applied OUTBOUND or INBOUND.
        # We assume Detector sees Inbound traffic before Tarpit, or Tarpit is applied to ACKs.)
        # Let's assume Detector sees the raw flow we generated (Inbound).
        detector.ingest([arrival_time])
        
        packet_idx += 1
        
        # Live Log
        if packet_idx % 1000 == 0:
            state = "ENGAGED" if effects["engaged"] else "MONITORING"
            print(f"T={t_sim:6.1f}s | Z={current_z:4.1f} | Latency={added_latency*1000:3.0f}ms | {state}")

    print("Simulation Complete.")
    
    # Plotting
    plot_results(history_t, history_z, history_lat, history_engaged, config.Z_THRESHOLD)

def plot_results(t, z, lat, eng, z_th):
    fig, axs = plt.subplots(3, 1, figsize=(10, 12), sharex=True)
    
    # Z-Score
    axs[0].plot(t, z, label='Detection Score (Z)', color='blue')
    axs[0].axhline(z_th, color='red', linestyle='--', label='Threshold')
    axs[0].set_ylabel('Confidence (Z)')
    axs[0].set_title('Mirage Surveillance')
    axs[0].legend()
    axs[0].grid(True)
    
    # Defense State
    axs[1].fill_between(t, eng, color='orange', alpha=0.5, label='Defense Active')
    axs[1].set_ylabel('State (0/1)')
    axs[1].set_title('Mirage Controller State')
    axs[1].grid(True)
    
    # Latency (Tarpit)
    axs[2].plot(t, lat, label='Artificial Latency', color='purple')
    axs[2].set_ylabel('Latency (ms)')
    axs[2].set_xlabel('Time (s)')
    axs[2].set_title('Countermeasure: Sawtooth Tarpit')
    axs[2].grid(True)
    
    plt.tight_layout()
    plt.savefig('mirage_simulation_report.png')
    print("Report saved to mirage_simulation_report.png")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Mirage Active Defense System")
    parser.add_argument('--sim', action='store_true', help='Run simulation mode')
    parser.add_argument('--monitor', action='store_true', help='Run live network monitor')
    parser.add_argument('--interface', type=str, default=None, help='Network interface to sniff (default: auto)')
    parser.add_argument('--duration', type=float, default=600.0, help='Duration in seconds (0 = infinite for monitor)')
    
    args = parser.parse_args()
    
    if args.sim:
        run_simulation(args.duration)
    elif args.monitor:
        run_live_monitor(args.interface, args.duration)
    else:
        print("Usage: python mirage_main.py --sim | --monitor")

