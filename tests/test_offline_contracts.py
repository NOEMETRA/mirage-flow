"""Offline contract tests. These do not capture traffic or validate field detection."""
import unittest

import numpy as np

from mirage.core import MirageConfig, PacketFlow, pn_key
from mirage.surveillance import (
    FlowDetector,
    PairwiseDelayEmbedder,
    TrafficTracker,
)
from mirage.countermeasures import ActiveDefenseController


class PacketFlowTests(unittest.TestCase):
    def test_interarrival_times(self):
        flow = PacketFlow(np.array([0.0, 0.1, 0.25]))
        np.testing.assert_allclose(flow.iats, [0.1, 0.15])

    def test_empty_interarrival_times(self):
        self.assertEqual(PacketFlow(np.array([0.0])).iats.size, 0)

    def test_key_has_expected_shape_and_alphabet(self):
        key = pn_key(32, seed=14)
        self.assertEqual(key.shape, (32,))
        self.assertTrue(set(key.tolist()).issubset({-1, 1}))


class TimingContractTests(unittest.TestCase):
    def test_embedder_preserves_packet_count_and_monotonicity(self):
        cfg = MirageConfig()
        cfg.BLOCK_SIZE = 8
        cfg.REPEATS = 2
        cfg.GAP_CHIPS = 2
        key = pn_key(cfg.BLOCK_SIZE, seed=17)
        flow = PacketFlow(np.arange(100, dtype=float) * 0.02)
        marked, repeats = PairwiseDelayEmbedder(cfg, key).embed(flow, start_idx=5)
        self.assertEqual(repeats, 2)
        self.assertEqual(marked.ts.size, flow.ts.size)
        self.assertTrue(np.all(np.diff(marked.ts) >= 0))
        self.assertTrue(np.all(np.isfinite(marked.ts)))

    def test_detector_returns_zero_when_window_is_too_short(self):
        cfg = MirageConfig()
        key = pn_key(cfg.BLOCK_SIZE, seed=2)
        detector = FlowDetector(cfg, key)
        detector.ingest([i * 0.02 for i in range(20)])
        self.assertEqual(detector.analyze(0.38), 0.0)

    def test_source_tracker_is_a_frequency_heuristic_only(self):
        tracker = TrafficTracker()
        self.assertEqual(tracker.get_dominant_ip(30, 10), "Unknown")
        tracker.add(1.0, "192.0.2.10")
        tracker.add(2.0, "192.0.2.11")
        tracker.add(3.0, "192.0.2.11")
        self.assertEqual(tracker.get_dominant_ip(10, 4), "192.0.2.11")
        self.assertEqual(tracker.get_dominant_ip(1, 10), "Unknown")


class ResponseModelTests(unittest.TestCase):
    def test_controller_hysteresis_is_modeled_not_applied(self):
        cfg = MirageConfig()
        ctl = ActiveDefenseController(cfg)
        below = ctl.update(cfg.Z_THRESHOLD - 3.0, 0.1)
        self.assertFalse(below["engaged"])
        self.assertEqual(below["latency_penalty"], 0.0)
        self.assertFalse(below["poison_active"])

        above = ctl.update(cfg.Z_THRESHOLD + 1.0, 0.1)
        self.assertTrue(above["engaged"])
        self.assertTrue(above["poison_active"])

        cooldown = ctl.update(cfg.Z_THRESHOLD - 1.0, 0.1)
        self.assertTrue(cooldown["engaged"])
        self.assertEqual(cooldown["reason"], "HYSTERESIS LOCK (COOLDOWN)")

        released = ctl.update(cfg.Z_THRESHOLD - 3.0, 0.1)
        self.assertFalse(released["engaged"])
        self.assertFalse(released["poison_active"])
        self.assertEqual(released["latency_penalty"], 0.0)


if __name__ == "__main__":
    unittest.main()
