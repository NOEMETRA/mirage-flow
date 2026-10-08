# Mirage Flow

**Experimental temporal-traffic analysis and response-modeling prototype.**

Mirage Flow is an independent, publicly documented single-developer research project for studying whether a known timing pattern can be recovered from packet inter-arrival times after the flow has been affected by jitter, delay, and packet loss.

The repository combines:

- a pairwise-delay watermark generator
- a stateful detector based on sliding correlation and Top-K peak fusion
- empirical background estimation with randomly generated comparison keys
- live packet-timestamp collection through Scapy
- a response-state model with hysteresis and bounded latency values
- controlled simulations used to inspect detector behavior

Mirage is a **research prototype**, not a production intrusion-detection or network-containment system. The current detector searches for a predefined temporal structure generated from a known key. It does not currently identify arbitrary covert channels or infer data exfiltration from timing alone.

## Research question

The main experiment is:

> Can a repeated pseudo-random timing pattern remain detectable when packet timing is distorted by realistic noise?

A secondary question is:

> Once a detector crosses a confidence threshold, how might a bounded and stateful response policy behave without immediately terminating the connection?

The repository explores both questions, but at different levels of maturity:

- **detection** is implemented and can be exercised in simulation or against captured packet timestamps;
- **response behavior** is represented as controller state and calculated effects;
- **actual traffic shaping or content injection** is not performed by the current CLI pipeline.

## Project status

| Area | Current status |
|---|---|
| Pairwise timing-pattern generation | Implemented |
| Stateful timestamp ingestion | Implemented |
| Sliding pairwise correlation | Implemented |
| Top-K peak fusion | Implemented |
| Wrong-key background estimation | Implemented |
| Controlled simulation | Implemented |
| Live packet timestamp collection | Implemented through Scapy |
| Source-IP context | Basic dominant-source heuristic |
| Hysteresis response controller | Implemented as a state model |
| Bounded latency calculation | Implemented as a calculated value |
| Kernel or proxy traffic shaping | Not implemented |
| Decoy delivery into live traffic | Not implemented |
| Arbitrary covert-channel discovery | Not implemented |
| Production readiness | Not claimed |

## How the experiment works

### 1. Timing-pattern generation

`PairwiseDelayEmbedder` modifies selected packet timestamps using a pseudo-noise key containing `+1` and `-1` values.

For each key element, one packet in a pair receives a small additional delay. Repeating this structure creates a temporal pattern that can later be searched for without inspecting packet payloads.

The default configuration is defined in `mirage/core.py`:

```python
WINDOW_SIZE = 60.0
ROBUST_A = 0.008
BLOCK_SIZE = 512
REPEATS = 16
GAP_CHIPS = 32
Z_THRESHOLD = 4.5
```

These values are experimental defaults rather than universal operating points.

### 2. Timestamp ingestion

`FlowDetector` receives packet timestamps and keeps a bounded history covering approximately two analysis windows.

The detector converts timestamps into inter-arrival times and derives two pairwise observation sequences, one for each possible pair alignment.

### 3. Sliding correlation

Each observation sequence is correlated with the known pseudo-noise key.

Because the exact phase can shift under timing noise, both pair alignments are evaluated and the stronger result is retained.

### 4. Top-K fusion

Instead of requiring every repeated block to align perfectly, the detector collects the strongest separated correlation peaks.

This is intended to preserve some signal energy when local timing distortion moves individual peaks away from their expected positions.

The number of peaks used is estimated from the amount of traffic present in the current window.

### 5. Empirical background

A raw correlation score is difficult to interpret without knowing the texture of the flow itself.

For every analysis pass, the detector therefore generates several random comparison keys and scores them against the same traffic. The real-key score is normalized relative to that local background:

```text
z = (real_score - background_mean) / background_std
```

This produces a flow-relative confidence value rather than a fixed raw-correlation threshold.

It is important to understand what this means: a high score indicates that the observed timing resembles the **known key** more strongly than the sampled wrong keys. It does not independently prove exfiltration, malware activity, operator identity, or malicious intent.

## Response model

`ActiveDefenseController` converts the detector score into a small state machine:

- engage when the score exceeds the configured threshold;
- remain engaged during a lower-confidence cooldown interval;
- disengage only after the score falls sufficiently below the threshold.

When engaged, the controller calculates:

- a bounded latency value following a sawtooth-like progression;
- a Boolean flag indicating that a decoy policy would be active.

The current implementation returns these values to the caller. It does **not** apply them to packets, operating-system queues, a transparent proxy, or firewall rules.

`SmartPoisonEngine` can generate byte sequences resembling fragments of a SQLite structure, but the current command-line workflow does not inject those bytes into any live stream.

This separation is intentional in the current research stage: detection and policy behavior can be studied without claiming that a complete containment layer exists.

## Source-IP context

The live monitor records observed source IP addresses and can report the most frequent source seen during a recent interval.

This is contextual telemetry only. It is not robust attribution. NAT, proxies, load balancers, shared endpoints, bidirectional traffic, and unrelated high-volume sources can all make the dominant address misleading.

## Repository structure

```text
mirage-flow/
├── mirage/
│   ├── core.py              # configuration, packet-flow type, key generation
│   ├── surveillance.py      # embedder, detector, live capture, source context
│   └── countermeasures.py   # response-state and decoy-data models
├── mirage_main.py           # simulation and live-monitor CLI
├── EVALUATION.md            # controlled test notes and recorded metrics
├── NEXUS-FLOW-v3_7_production.ipynb
└── requirements.txt
```

The notebook contains earlier algorithm-development material and should be treated as a research reference rather than a separate production implementation.

## Offline validation

The repository now includes a narrow, repeatable contract suite for the **software model**:

```bash
python -m pip install "numpy>=1.24,<3"
python -m unittest discover -s tests -v
```

These tests exercise timestamp handling, synthetic embedding invariants, short-window detector behavior, source-frequency context, and the hysteresis controller. CI also compiles Python sources. The suite intentionally does **not** sniff interfaces, transmit packets, apply traffic shaping, or contact a third-party target.

Passing these tests means only that the selected software contracts held under the test conditions. It does **not** establish covert-channel discovery, real-network detection performance, or operational containment.

## Requirements

- Python 3.8+
- NumPy
- Matplotlib
- Scapy for live capture
- Npcap on Windows or libpcap-compatible capture support on Linux/macOS
- elevated privileges when required by the operating system or capture interface

Install the Python dependencies:

```bash
python -m pip install -r requirements.txt
```

## Running the controlled simulation

```bash
python mirage_main.py --sim
```

Set a custom duration:

```bash
python mirage_main.py --sim --duration 600
```

The simulation:

1. generates a synthetic packet timeline;
2. adds timing jitter;
3. inserts the known pairwise pattern after part of the run;
4. streams timestamps into the detector;
5. records confidence, controller state, and calculated latency;
6. writes `mirage_simulation_report.png`.

The simulation is useful for inspecting algorithm behavior and regressions. It is not evidence that the same performance will transfer unchanged to internet traffic, encrypted applications, VPNs, wireless congestion, or adversarial channels using unrelated encoding schemes.

## Running the live monitor

Continuous monitoring on the automatically selected interface:

```bash
python mirage_main.py --monitor --duration 0
```

Monitoring a named interface:

```bash
python mirage_main.py --monitor --interface "Ethernet" --duration 600
```

The live mode currently:

- captures packet timestamps;
- feeds them to the known-key detector;
- calculates a detector score;
- updates the response-state model;
- prints packet count, score, modeled latency, state, and basic source context.

It does not delay, rewrite, redirect, terminate, or inject data into the monitored traffic.

## Console states

### `MONITORING`

The current detector score is below the engagement threshold.

### `THREAT DETECTED (Z-SCORE)`

The known-key similarity score is above the configured threshold. The name is retained by the code, but should be interpreted as **pattern detected under the current model**, not as a confirmed security incident.

### `HYSTERESIS LOCK (COOLDOWN)`

The score has fallen below the engagement threshold but not far enough to reset the controller. This prevents rapid state changes near the boundary.

## Evaluation notes

`EVALUATION.md` records results from controlled synthetic scenarios and a limited live-LAN observation period.

Those values should be read with the following constraints:

- the positive samples contain the same known-key pattern used by the detector;
- several scenarios use synthetic Gaussian timing noise;
- “0 false positives observed” describes the finite test window, not a proven zero false-positive rate;
- the live-LAN observation did not establish broad traffic diversity;
- the evaluation does not cover arbitrary timing channels, all network conditions, or adaptive adversaries;
- the detector score depends on traffic volume, flow structure, key length, window size, and the random wrong-key sample.

The current evaluation is best understood as an internal algorithm test matrix.

## Known limitations

- Detection requires the expected pseudo-noise key.
- The model does not learn unknown timing encodings.
- Packet timestamps are grouped globally rather than through a mature per-flow five-tuple pipeline.
- Source-IP context uses a frequency heuristic rather than causal attribution.
- Background estimation generates random keys during analysis and may be computationally expensive.
- Randomness is not fully isolated through local random-generator instances.
- The default threshold is calibrated only against the included experiments.
- Timing distributions on real networks are often non-Gaussian, bursty, multimodal, and application-dependent.
- Live capture behavior depends on interface, driver, operating system, privileges, and timestamp quality.
- Response effects are modeled but not enforced on network traffic.
- Decoy generation is not connected to a delivery mechanism.
- There is no current automated CI or broad reproducibility harness.

## Intended use

Mirage Flow is intended for:

- private research into packet-timing patterns;
- controlled simulation;
- authorized laboratory traffic capture;
- studying correlation under jitter and loss;
- experimenting with stateful response policies without applying them to real traffic.

Use live capture only on systems and networks you own or are explicitly authorized to observe.

## Development approach

This repository is maintained by a single developer as an experimental research notebook expressed in code.

The next meaningful research steps are not additional claims, but stronger falsification:

- evaluate unrelated timing-channel families;
- split traffic into explicit flows;
- test non-Gaussian and application-derived baselines;
- compare against simpler matched-filter and anomaly-detection baselines;
- measure stability across multiple random seeds;
- separate detector calibration from evaluation datasets;
- connect any future response mechanism only inside an isolated proxy or network namespace;
- document negative results alongside successful ones.

## License

See the repository license, when present, for the current terms of use.
