"""Reproduce six underground rooms over a continuous November shift log."""

from datetime import datetime, timedelta
from math import sin
from random import Random


def demo_rows() -> list[dict]:
    rng = Random(77208)
    starting = datetime(2026, 11, 12, 0, 0)
    rooms = (
        ("C01 票证盒架", 53, 12, 51),
        ("C02 地图长卷", 65, 23, 56),
        ("C03 套片抽屉", 54, 10, 50),
        ("C04 海报平柜", 58, 19, 52),
        ("C05 装订纸样", 52, 7, 50),
        ("C06 包装底片", 49, 5, 43),
    )
    state = {room: humidity for room, humidity, _, _ in rooms}
    rows = []
    shifts = 41
    for phase in range(shifts):
        stamp = starting + timedelta(hours=8 * phase)
        outdoor = 62 + 13 * sin(phase / 3.7) + rng.gauss(0, 2.5)
        for room_number, (room, _, door_average, base) in enumerate(rooms, 1):
            door = max(0, door_average + (8 if stamp.hour == 8 else -4) + rng.gauss(0, 5))
            last = state[room]
            if phase == shifts - 1 and room_number == 2:
                door = 42
            if phase == shifts - 1 and room_number == 6:
                door = 4

            rows.append({
                "sample_id": f"CQ-{room_number:02d}-{phase + 1:02d}",
                "room": room,
                "shift_at": stamp.strftime("%Y-%m-%d %H:%M"),
                "inside_rh": round(last, 2),
                "outside_rh": round(outdoor, 2),
                "door_minutes": round(door, 2),
            })
            cycle = {0: 0.8, 8: 1.2, 16: -1.5}[stamp.hour]
            state[room] = (
                0.75 * last + 0.25 * base + 0.18 * (outdoor - 60) +
                0.18 * door + cycle + rng.gauss(0, 0.72)
            )
    return rows


def demo_calibration(room: str, bias: float = 2.0, shifts: int = 4, manual: bool = False) -> list[dict]:
    """构造一段换表同抄演示数据：新表系统性偏低 ``bias`` 个百分点。

    时间取演示序列最后 ``shifts`` 个班次端点；``manual=True`` 时只给一班，
    因留不出核验班次而触发人工复测分支。
    """
    count = 1 if manual else shifts
    last = datetime(2026, 11, 12, 0, 0) + timedelta(hours=8 * (41 - count))
    entries = []
    for phase in range(count):
        stamp = last + timedelta(hours=8 * phase)
        old_value = round(56 + 0.4 * phase, 2)
        entries.append({
            "room": room,
            "shift_at": stamp.strftime("%Y-%m-%d %H:%M"),
            "old_rh": old_value,
            "new_rh": round(old_value - bias, 2),
        })
    return entries
