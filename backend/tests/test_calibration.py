"""Standard-library only checks for the hygrometer swap calibration logic.

Run with: python3 tests/test_calibration.py
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from business.calibration import (  # noqa: E402
    MAX_CHECK_RESIDUAL,
    build_calibrations,
    calibrate_rows,
    group_readings,
    recheck_rooms,
)


def entry(room, shift, old, new):
    return {"room": room, "shift_at": shift, "old_rh": old, "new_rh": new}


class CalibrationTests(unittest.TestCase):
    def test_constant_bias_passes_split(self):
        # 新表系统性低 2 个百分点，前段估偏差、末段核验应通过。
        entries = [
            entry("C01", f"2026-11-2{day} 08:00", 60.0, 58.0)
            for day in range(1, 7)
        ]
        rooms = build_calibrations(entries)
        self.assertEqual(len(rooms), 1)
        room = rooms[0]
        self.assertTrue(room.valid)
        self.assertFalse(room.manual_recheck)
        self.assertAlmostEqual(room.bias, 2.0)
        self.assertGreaterEqual(room.check_shift_count, 1)
        self.assertGreaterEqual(room.fit_shift_count, 1)
        self.assertEqual(room.fit_shift_count + room.check_shift_count, 6)

    def test_duplicate_same_shift_counted_once(self):
        entries = [
            entry("C01", "2026-11-21 08:00", 60.0, 58.0),
            entry("C01", "2026-11-21 08:00", 99.0, 1.0),  # 同班重复，应被忽略
            entry("C01", "2026-11-22 08:00", 61.0, 59.0),
        ]
        grouped = group_readings(entries)
        self.assertEqual(len(grouped["C01"]), 2)
        self.assertEqual(grouped["C01"][0].old_rh, 60.0)

    def test_insufficient_shifts_for_check_goes_manual(self):
        entries = [entry("C02", "2026-11-21 08:00", 60.0, 59.0)]
        rooms = build_calibrations(entries)
        self.assertFalse(rooms[0].valid)
        self.assertTrue(rooms[0].manual_recheck)
        self.assertIsNone(rooms[0].bias)
        self.assertEqual(recheck_rooms(rooms), ["C02"])

    def test_check_residual_over_two_points_goes_manual(self):
        # 前段稳定偏差 2，末段核验班残差恰好超过 2 个百分点。
        entries = [entry("C03", f"2026-11-2{d} 08:00", 60.0, 58.0) for d in range(1, 5)]
        entries.append(entry("C03", "2026-11-25 08:00", 60.0, 55.0))  # 差值 5，残差 3
        rooms = build_calibrations(entries)
        room = rooms[0]
        self.assertTrue(room.manual_recheck)
        self.assertFalse(room.valid)
        self.assertGreater(room.check_residual_max, MAX_CHECK_RESIDUAL)

    def test_boundary_residual_equal_two_passes(self):
        # 残差恰好等于 2.0 不算超限。
        entries = [
            entry("C04", "2026-11-21 08:00", 60.0, 60.0),
            entry("C04", "2026-11-22 08:00", 62.0, 60.0),  # 差值 2，偏差 0，残差恰为 2
        ]
        room = build_calibrations(entries)[0]
        self.assertTrue(room.valid)
        self.assertEqual(room.check_residual_max, 2.0)

    def test_calibrate_rows_shifts_only_post_swap_new_readings(self):
        entries = [entry("C05", f"2026-11-2{d} 08:00", 60.0, 58.0) for d in range(1, 5)]
        rooms = build_calibrations(entries)
        switched = rooms[0].switched_at.strftime("%Y-%m-%d %H:%M")
        rows = [
            # 换表前历史行，不动。
            {"sample_id": "A", "room": "C05", "shift_at": "2026-11-20 08:00", "inside_rh": 50.0},
            # 同抄期内的行，保持原值。
            {"sample_id": "B", "room": "C05", "shift_at": "2026-11-21 08:00", "inside_rh": 58.0},
            # 换表时点当班（最后一条同抄），保持原值。
            {"sample_id": "C", "room": "C05", "shift_at": switched, "inside_rh": 58.0},
            # 换表后新表读数，加偏差 +2。
            {"sample_id": "D", "room": "C05", "shift_at": "2026-11-25 08:00", "inside_rh": 57.0},
            # 别的库房不受影响。
            {"sample_id": "E", "room": "C06", "shift_at": "2026-11-25 08:00", "inside_rh": 49.0},
        ]
        corrected, changed = calibrate_rows(rows, rooms)
        by_id = {row["sample_id"]: row for row in corrected}
        self.assertEqual(by_id["A"]["inside_rh"], 50.0)
        self.assertEqual(by_id["B"]["inside_rh"], 58.0)
        self.assertEqual(by_id["C"]["inside_rh"], 58.0)
        self.assertEqual(by_id["D"]["inside_rh"], 59.0)
        self.assertEqual(by_id["E"]["inside_rh"], 49.0)
        self.assertEqual(changed, {"D"})

    def test_manual_room_rows_are_not_corrected(self):
        entries = [entry("C06", "2026-11-21 08:00", 60.0, 59.0)]
        rooms = build_calibrations(entries)
        rows = [{"sample_id": "X", "room": "C06", "shift_at": "2026-11-25 08:00", "inside_rh": 57.0}]
        corrected, changed = calibrate_rows(rows, rooms)
        self.assertEqual(corrected[0]["inside_rh"], 57.0)
        self.assertEqual(changed, set())

    def test_invalid_endpoint_rejected(self):
        with self.assertRaises(ValueError):
            group_readings([entry("C01", "2026-11-21 09:00", 60.0, 58.0)])

    def test_record_serialisation_roundtrip(self):
        entries = [entry("C01", f"2026-11-2{d} 08:00", 60.0, 58.0) for d in range(1, 5)]
        record = build_calibrations(entries)[0].to_record()
        self.assertEqual(record["room"], "C01")
        self.assertEqual(len(record["readings"]), 4)
        self.assertIn("bias", record)

    def test_snapshot_staleness_contract(self):
        # Mirrors src.services.calibrations.is_run_stale without importing SQLAlchemy.
        def snapshot_key(snapshot):
            return {
                (item["calibration_id"], item["room"]):
                (item["valid"], item["manual_recheck"], item["bias"])
                for item in snapshot
            }

        def is_stale(previous, current):
            if not current:
                return False
            return snapshot_key(previous) != snapshot_key(current)

        current = [{"calibration_id": "cal-1", "room": "C01", "valid": True,
                    "manual_recheck": False, "bias": 2.0}]
        # Legacy run with no snapshot, calibrations now exist -> stale.
        self.assertTrue(is_stale([], current))
        # Nothing calibrated yet -> never stale.
        self.assertFalse(is_stale([], []))
        # Same snapshot -> still valid.
        self.assertFalse(is_stale(current, current))
        # A new calibration changes the bias -> stale, must be recomputed.
        updated = [{**current[0], "bias": 2.5}]
        self.assertTrue(is_stale(current, updated))


if __name__ == "__main__":
    unittest.main(verbosity=2)
