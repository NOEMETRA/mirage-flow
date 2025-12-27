# 🛡️ MIRAGE: Adaptive Network Containment System (v4.1.0)

**Mirage** is a **Behavioral Counter-Espionage Framework** designed to identify and mitigate advanced covert channels. It operates by analyzing the temporal characteristics of network flows to detect anomalies associated with data exfiltration, independent of payload encryption.

> See [EVALUATION.md](EVALUATION.md) for detailed performance metrics, threat models, and test matrices.

## 🎯 System Capabilities

### 1. 👁️ Physics-Based Surveillance
*   **Temporal Flow Analysis**: Utilizes **Robust Top-K Fusion** to identify statistical anomalies in Inter-Arrival Times (IAT), enabling detection of low-bandwidth watermarks within encrypted streams (HTTPS/VPN).
*   **Attribution**: Correlates detection events with Source IP addresses for immediate incident response context.
*   **High-Confidence Operating Point**: Calibrated at **Z-Threshold = 4.5**. In controlled tests (Gaussian Noise $\sigma \le 10ms$), this configuration yielded **0 False Positives** over extended observation windows.

### 2. 🥊 Adaptive Containment Policies ("Active Defense")
Upon confirming a threat with high statistical confidence, Mirage initiates a non-disruptive containment protocol:

*   **Bounded Latency Shaping**: Rather than terminating connections (which provides immediate feedback to the adversary), Mirage introduces a modulated latency penalty (0-500ms) following a **Sawtooth Hysteresis** curve. This degrades the channel's effective bandwidth while maintaining connection state (`ESTABLISHED`).
*   **Decoy Artifact Injection**: (Optional) Injects statistically plausible but semantically invalid data structures (e.g., randomized SQLite pages) into the stream, targeting the data integrity of the exfiltration attempt.

## 📂 Project Structure

*   `mirage/` - **Core Package**.
    *   `core.py`: Configuration and Types.
    *   `surveillance.py`: Detection Engine (Top-K Fusion).
    *   `countermeasures.py`: Containment Engine (Latency Shaping / Decoy Injection).
*   `mirage_main.py` - **CLI Entry Point**.
*   `NEXUS-FLOW-v3_7_production.ipynb` - **Algorithm Reference**.

## 🚀 Usage

### Prerequisites
*   Python 3.8+
*   **Npcap** (Windows) or **libpcap** (Linux/Mac).
*   Administrator Privileges.

### 1. Verification & Testing
Before deployment, it is recommended to run the simulation suite to validate performance against the baseline threat model.
```bash
python mirage_main.py --sim
```

### 2. Live Monitoring
Deploy the sensor in continuous monitoring mode.
```bash
# Continuous Operation
python mirage_main.py --monitor --duration 0

# Targeted Interface
python mirage_main.py --monitor --interface "Ethernet"
```

## 🧠 Diagnostic Codes

*   **`THREAT DETECTED (Z-SCORE)`**: Statistical anomaly exceeds confidence threshold ($Z > 4.5$).
*   **`HYSTERESIS LOCK (COOLDOWN)`**: Containment policy remains active due to hysteresis timer, preventing state flapping.

---
*Developed by NEXUS Defense Project*
