# System Evaluation & Performance Metrics

This document details the performance characteristics of the **Mirage Active Defense System (v4.1.0)** under controlled test conditions and simulated environments.

## 1. Test Matrix

Evaluation performed using `mirage.surveillance.FlowDetector` (v3.7 Core) against various channel models.

| Scenario | Environment Model | Conditions | Duration | Flow Count | Result (TPR / FPR) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **S1: Baseline** | Gaussian Channel | Jitter $\sigma \le 5ms$ | 600s | 100 | **100% / 0%** |
| **S2: High Noise** | Gaussian Channel | Jitter $\sigma = 10ms$ | 600s | 100 | **93% / 0%** |
| **S3: Hard Point** | Wireless/Congested | Jitter $\sigma = 10ms$ + Delay $\delta = 40ms$ | 150s | 100 | **69% / 0%** |
| **S4: Burst Loss** | Gilbert-Elliot Model | Loss Probability $p=15\%$ | 600s | 50 | **98% / 0%** |
| **S5: Production** | Live LAN Monitor | Real Traffic (Mixed) | ~1 hr | N/A | **0 FP Observed** |

> **Note**: "0 FP Observed" refers to zero false positive engagements (Z > 4.5) during the specific test windows defined above.

## 2. Threat Model Coverage

Mirage is designed to detect specific classes of **Timing-Based Covert Channels**.

### In Scope (Covered)
*   ✅ **Inter-Arrival Time (IAT) Watermarks**: Steganographic modulation of packet delays to encode hidden data.
*   ✅ **Low-Frequency Beacons**: Periodic signaling hidden within legitimate traffic streams (e.g., HTTPS Keep-Alive abuse).
*   ✅ **Tunneling Anomalies**: SSH/VPN tunnels exhibiting non-interactive timing signatures consistent with automated exfiltration.

### Out of Scope (Not Covered)
*   ❌ **Payload Inspection**: Mirage does not inspect packet contents (DPI). It is agnostic to the data being transferred (e.g., malware signatures).
*   ❌ **Single-Packet Attacks**: The system requires a flow of packets (Window Size: 60s) to perform statistical correlation.
*   ❌ **L7 Application Logic**: Does not detect SQL Injection or XSS unless they generate timing anomalies.

## 3. Key Metrics

### False Positive Rate (FPR)
*   **Operating Point**: Z-Threshold = 4.5.
*   **Observed**: 0.00 detections/hour in baseline noise tests (Gaussian $\sigma=10ms$).
*   **Theoretical**: At Z=4.5, assuming Gaussian noise distribution, $P(FP) \approx 3.4 \times 10^{-6}$.

### True Positive Rate (TPR)
*   **Ideal Conditions**: 100% (Jitter < 5ms).
*   **Degraded Conditions**: >65% (Jitter 10ms + 40ms Adversarial Delay).
*   **Recovery**: The **Robust Top-K Fusion** algorithm allows signal recovery even when individual watermark peaks are shifted by up to 2x the chip width.

### Detection Latency
*   **Window Size**: 60.0 seconds.
*   **Time to Engage**: Typically 1.5 - 2.0 windows (90-120s) required to accumulate sufficient Z-Score confidence for active engagement.

## 4. Algorithmic Baseline

The **Top-K Fusion** architecture was selected after comparative analysis:

*   **Comb-Sum**: Failed in high-jitter scenarios (TPR < 15%) due to strict grid alignment requirements.
*   **Soft-Comb**: Improved tolerance but increased noise floor (FPR > 5%).
*   **Top-K Fusion (Current)**: Achieved optimal balance by "harvesting" peak correlation energy within valid windows, tolerating localized jitter while enforcing global structure.

## 5. Reproducibility

To reproduce the "Battle Royale" simulation results (Scenario S1/S2 mixed):

```bash
# Run the integrated simulation
python mirage_main.py --sim
```

**Parameters**:
*   `SEED`: 42
*   `WINDOW_SIZE`: 60.0s
*   `BLOCK_SIZE`: 512
*   `REPEATS`: Dynamic (Target 16)
