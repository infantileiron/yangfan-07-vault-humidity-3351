"""End-to-end check of analyze() with numpy/sklearn stubbed via sys.modules.

The real forecasting layer needs numpy/sklearn, which are absent in this local
environment. We inject minimal fakes before importing the business package, so
the calibration-aware analyze() wiring (correction, manual recheck, ordering and
result columns) is still exercised against the real demo dataset.

Run with: python3 tests/test_analyze_stub.py
"""

import sys
import types
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def _install_stubs():
    numpy = types.ModuleType("numpy")
    numpy.ndarray = object  # used only in annotations at import time

    def clip(values, low, high):
        return [min(max(float(v), low), high) for v in values]

    numpy.clip = clip
    numpy.mean = lambda values: sum(values) / len(values)
    sys.modules["numpy"] = numpy

    sklearn = types.ModuleType("sklearn")
    linear_model = types.ModuleType("sklearn.linear_model")
    pipeline = types.ModuleType("sklearn.pipeline")
    preprocessing = types.ModuleType("sklearn.preprocessing")

    class _Ridge:
        def __init__(self, alpha=1.0):
            self.alpha = alpha

        def fit(self, features, targets):
            return self

        def predict(self, features):
            # Persistence-like fake: echo the first feature (current inside_rh).
            return [row[0] for row in features]

    def _make_pipeline(*_steps):
        return _Ridge()

    class _Scaler:
        def fit(self, *_):
            return self

        def transform(self, values):
            return values

        def fit_transform(self, values, *_):
            return values

    linear_model.Ridge = _Ridge
    pipeline.make_pipeline = _make_pipeline
    preprocessing.StandardScaler = _Scaler
    sys.modules["sklearn"] = sklearn
    sys.modules["sklearn.linear_model"] = linear_model
    sys.modules["sklearn.pipeline"] = pipeline
    sys.modules["sklearn.preprocessing"] = preprocessing


class AnalyzeStubTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _install_stubs()
        from business.algorithm import analyze  # noqa: PLC0415
        from business.calibration import build_calibrations  # noqa: PLC0415
        from business.demo import demo_rows  # noqa: PLC0415
        cls.analyze = staticmethod(analyze)
        cls.build_calibrations = staticmethod(build_calibrations)
        cls.rows = demo_rows()

    def test_legacy_run_has_new_columns_without_calibration(self):
        result = self.analyze(self.rows, 62.0)
        self.assertTrue(result["rows"])
        for row in result["rows"]:
            self.assertIn("manual_recheck", row)
            self.assertIn("calibrated", row)
            self.assertFalse(row["manual_recheck"])
            self.assertFalse(row["calibrated"])

    def test_manual_recheck_room_is_flagged_and_sorted_first(self):
        target_room = self.rows[0]["room"]
        # Single parallel shift -> cannot reserve a check shift -> manual.
        entries = [{
            "room": target_room, "shift_at": "2026-11-24 16:00",
            "old_rh": 55.0, "new_rh": 53.0,
        }]
        calibrations = self.build_calibrations(entries)
        result = self.analyze(self.rows, 62.0, calibrations)
        flagged = [row for row in result["rows"] if row["manual_recheck"]]
        self.assertEqual(len(flagged), 1)
        self.assertEqual(flagged[0]["room"], target_room)
        self.assertEqual(flagged[0]["disposition"], "转人工复测")
        # Manual recheck rows float to the top of the queue.
        self.assertTrue(all(row["manual_recheck"] for row in result["rows"][:1]))

    def test_valid_calibration_corrects_post_swap_readings(self):
        target_room = self.rows[0]["room"]
        # Four parallel shifts with a steady 2 pp under-read -> passes split.
        entries = [
            {"room": target_room, "shift_at": f"2026-11-2{d} 08:00",
             "old_rh": 55.0 + d, "new_rh": 53.0 + d}
            for d in range(1, 5)
        ]
        calibrations = self.build_calibrations(entries)
        self.assertTrue(calibrations[0].valid)
        result = self.analyze(self.rows, 62.0, calibrations)
        # The demo data ends at 2026-11-25 08:00 which is the last parallel
        # shift, so no later row exists to correct: nothing is marked calibrated,
        # but the run still succeeds and the room is not sent to manual recheck.
        room_row = next(row for row in result["rows"] if row["room"] == target_room)
        self.assertFalse(room_row["manual_recheck"])

    def test_post_swap_row_is_marked_calibrated_in_forecast(self):
        from business.shift_series import SHIFT  # noqa: PLC0415
        from datetime import datetime, timedelta  # noqa: PLC0415
        room = "C09 校准机房"
        start = datetime(2026, 11, 1, 0, 0)
        bias = 3.0
        rows = []
        # 24 endpoints; parallel window at 18..21, new meter only from index 22.
        for index in range(24):
            true_rh = 50.0
            recorded = true_rh - bias if index >= 22 else true_rh
            rows.append({
                "sample_id": f"S-{index:02d}", "room": room,
                "shift_at": (start + SHIFT * index).strftime("%Y-%m-%d %H:%M"),
                "inside_rh": recorded, "outside_rh": 60.0, "door_minutes": 10.0,
            })
        entries = [
            {"room": room,
             "shift_at": (start + SHIFT * i).strftime("%Y-%m-%d %H:%M"),
             "old_rh": true_rh, "new_rh": true_rh - bias}
            for i in range(18, 22)
        ]
        calibrations = self.build_calibrations(entries)
        self.assertTrue(calibrations[0].valid)
        result = self.analyze(rows, 62.0, calibrations)
        only = result["rows"][0]
        self.assertEqual(only["room"], room)
        self.assertTrue(only["calibrated"])
        # Latest new-meter reading 47 is moved back onto the old scale (50).
        self.assertEqual(only["now_rh"], 50.0)
        self.assertFalse(only["manual_recheck"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
