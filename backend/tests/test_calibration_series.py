"""Integration checks between calibration correction and the series builder.

Both business.calibration and business.shift_series use only the standard
library, so this runs without numpy/sklearn and proves the corrected rows still
satisfy the continuous-shift contract and keep humidity changes on one scale.

Run with: python3 tests/test_calibration_series.py
"""

import sys
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from business.calibration import build_calibrations, calibrate_rows  # noqa: E402
from business.shift_series import SHIFT, form_series  # noqa: E402

START = datetime(2026, 11, 1, 0, 0)
FMT = "%Y-%m-%d %H:%M"


def stamp(index):
    return (START + SHIFT * index).strftime(FMT)


def true_rh(index):
    return round(50.0 + 0.1 * index, 2)


class CalibrationSeriesTests(unittest.TestCase):
    def _series(self, room, new_meter_start, bias):
        # 28 continuous endpoints. The old meter stays authoritative through the
        # parallel window; the new (under-reading) meter is recorded from new_meter_start.
        rows = []
        for index in range(28):
            recorded = true_rh(index) - bias if index >= new_meter_start else true_rh(index)
            rows.append({
                "sample_id": f"{room}-{index:02d}", "room": room,
                "shift_at": stamp(index), "inside_rh": round(recorded, 2),
                "outside_rh": 60.0, "door_minutes": 10.0,
            })
        return rows

    def test_corrected_series_keeps_continuity_and_scale(self):
        room = "C01"
        bias = 3.0
        # Parallel overlap at 20..23; correction applies from index 24 onward.
        parallel = range(20, 24)
        new_meter_start = 24
        rows = self._series(room, new_meter_start, bias)
        entries = [
            {"room": room, "shift_at": stamp(i), "old_rh": true_rh(i),
             "new_rh": round(true_rh(i) - bias, 2)}
            for i in parallel
        ]
        rooms = build_calibrations(entries)
        self.assertTrue(rooms[0].valid)
        self.assertAlmostEqual(rooms[0].bias, bias)
        corrected, changed = calibrate_rows(rows, rooms)

        # Only rows strictly after the last parallel shift are corrected.
        self.assertEqual(changed, {f"{room}-{i}" for i in range(24, 28)})
        history, next_shift = form_series(corrected)
        self.assertTrue(history)
        self.assertEqual(next_shift[0].current.room, room)

        # The meter swap no longer introduces a jump: every step stays ~0.1 pp,
        # i.e. the new-meter readings have been moved onto the old-meter scale.
        by_index = {row["sample_id"]: row["inside_rh"] for row in corrected}
        for index in (23, 24, 25):
            delta = by_index[f"{room}-{index + 1}"] - by_index[f"{room}-{index}"]
            self.assertAlmostEqual(delta, 0.1, places=1)
        self.assertAlmostEqual(by_index[f"{room}-27"], true_rh(27), places=1)

    def test_manual_recheck_room_passes_through_uncorrected(self):
        room = "C02"
        rows = self._series(room, 24, 3.0)
        # Only one parallel shift -> cannot reserve a check shift -> manual.
        entries = [{"room": room, "shift_at": stamp(20), "old_rh": true_rh(20),
                    "new_rh": round(true_rh(20) - 3.0, 2)}]
        rooms = build_calibrations(entries)
        self.assertTrue(rooms[0].manual_recheck)
        corrected, changed = calibrate_rows(rows, rooms)
        self.assertEqual(changed, set())
        # Uncorrected but structurally valid series still builds.
        history, _ = form_series(corrected)
        self.assertTrue(history)


if __name__ == "__main__":
    unittest.main(verbosity=2)
