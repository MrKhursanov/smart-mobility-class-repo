"""Meaningful pure-logic tests; does not substitute for a ROS graph test."""
import unittest
from smart_hub_m1.core import QueueEngine, inside, QUEUE, features, Predictor
from smart_hub_m1.scenario import observations


class TestPerception(unittest.TestCase):
    def test_polygon_boundary_and_outside(self):
        self.assertTrue(inside((2., 5.), QUEUE))
        self.assertTrue(inside((4., 6.), QUEUE))
        self.assertFalse(inside((6.1, 6.), QUEUE))

    def test_s1_sequence_and_freeze(self):
        e = QueueEngine()
        wanted = {0: 0, 60: 3, 110: 5, 160: 4, 250: 4}
        for k in range(401):
            t = k/10
            if t < 30:
                e.observe(observations(t)[0], t, t)
            state = e.state(t)
            if k in wanted:
                self.assertTrue(state.valid)
                self.assertEqual(state.count, wanted[k])
            if k == 311:
                self.assertFalse(state.valid)
                self.assertLess(state.stamp, 30.)

    def test_short_occlusion_and_duplicate_ids(self):
        e = QueueEngine()
        for k in range(11):
            t = k/10
            rows = [] if .6 <= t < .9 else [('a', 3., 6., 1.)]*2
            e.observe(rows, t, t)
            if k >= 4:
                self.assertEqual(e.state(t).count, 1)

    def test_disappearance_not_retained_indefinitely(self):
        e = QueueEngine()
        for k in range(16):
            t = k/10
            e.observe([('a', 3., 6., 1.)] if t < .8 else [], t, t)
        self.assertEqual(e.state(1.5).count, 0)

    def test_repeated_stamp_does_not_refresh_watchdog(self):
        e = QueueEngine()
        e.observe([], 0., 0.)
        e.observe([], 0., 1.1)
        self.assertFalse(e.state(1.1).valid)

    def test_future_out_of_order_and_invalid_values(self):
        e = QueueEngine()
        self.assertFalse(e.observe([], 2., 0., source_now=0.))
        e.observe([], 1., 1.)
        self.assertFalse(e.observe([], .9, 1.1))
        self.assertFalse(e.observe([('bad', float('nan'), 6., 1.)], 1.2, 1.2) and e.state(1.2).valid)

    def test_low_confidence_is_unknown(self):
        e = QueueEngine()
        e.observe([('a', 3., 6., .2)], 0., 0.)
        self.assertFalse(e.state(0.).valid)

    def test_crossing_immediate_and_clear_debounce(self):
        e = QueueEngine()
        e.observe([('ped', 5., 3., 1.)], 0., 0.)
        self.assertTrue(e.state(0.).crossing_occupied)
        for k in range(1, 22):
            t = k/10
            e.observe([], t, t)
            self.assertEqual(e.state(t).crossing_occupied, k < 21)

    def test_gap_cannot_prove_crossing_clear(self):
        e = QueueEngine()
        e.observe([], 0., 0.)
        e.observe([], 3., 3.)
        self.assertTrue(e.state(3.).crossing_occupied)

    def test_zone_exit_is_debounced(self):
        e = QueueEngine()
        for k in range(6):
            e.observe([('a', 3., 6., 1.)], k/10, k/10)
        e.observe([('a', 7., 6., 1.)], .6, .6)
        self.assertEqual(e.state(.6).count, 1)
        for k in range(7, 11):
            e.observe([('a', 7., 6., 1.)], k/10, k/10)
        self.assertEqual(e.state(1.).count, 0)


class TestPrediction(unittest.TestCase):
    def test_features_are_causal_and_exact(self):
        x = features(list(range(60)))
        self.assertEqual(list(x), [59., 54.5, 10., 30., 0.])

    def test_no_short_history_or_bad_counts(self):
        with self.assertRaises(ValueError):
            features([1]*59)
        with self.assertRaises(ValueError):
            features([-1]*60)

    def test_warmup_stale_and_rewarm(self):
        p = Predictor({'selected': 'persistence'})
        for t in range(59):
            self.assertIsNone(p.tick(3, True, t))
        self.assertEqual(p.tick(3, True, 59), (3., 3.))
        self.assertIsNone(p.tick(3, False, 60))
        self.assertIsNone(p.tick(3, True, 61))

    def test_gap_resets_history(self):
        p = Predictor({'selected': 'persistence'})
        for t in range(60):
            p.tick(3, True, t)
        self.assertIsNone(p.tick(3, True, 70))


if __name__ == '__main__':
    unittest.main()
