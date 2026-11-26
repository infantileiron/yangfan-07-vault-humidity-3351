"""Validate shift readings and form examples using only observations known at issue time."""

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from math import cos, pi, sin


SHIFT = timedelta(hours=8)
TIME_FORMAT = "%Y-%m-%d %H:%M"


@dataclass(frozen=True)
class Reading:
    sample_id: str
    room: str
    at: datetime
    inside_rh: float
    outside_rh: float
    door_minutes: float


@dataclass(frozen=True)
class ShiftInputs:
    current: Reading
    previous: Reading

    @property
    def target_at(self) -> datetime:
        return self.current.at + SHIFT

    @property
    def features(self) -> tuple[float, ...]:
        phase = self.target_at.hour / 24 * 2 * pi
        return (
            self.current.inside_rh,
            self.current.inside_rh - self.previous.inside_rh,
            self.current.outside_rh,
            self.current.door_minutes,
            sin(phase),
            cos(phase),
        )


@dataclass(frozen=True)
class Example:
    inputs: ShiftInputs
    actual_rh: float


def form_series(rows: list[dict]) -> tuple[list[Example], list[ShiftInputs]]:
    groups = defaultdict(list)
    for row in rows:
        sample_id = row["sample_id"]
        try:
            observed_at = datetime.strptime(row["shift_at"], TIME_FORMAT)
        except (ValueError, TypeError) as exc:
            raise ValueError(f"{sample_id} 的读数时间应使用 YYYY-MM-DD HH:MM。") from exc
        if observed_at.strftime(TIME_FORMAT) != row["shift_at"] or observed_at.hour not in (0, 8, 16) or observed_at.minute:
            raise ValueError(f"{sample_id} 的班次端点应为 00:00、08:00 或 16:00。")
        room = row["room"]
        groups[room].append(Reading(
            sample_id, room, observed_at,
            float(row["inside_rh"]), float(row["outside_rh"]), float(row["door_minutes"]),
        ))

    if not groups:
        raise ValueError("至少需要一个库房的连续交班读数。")
    expected_latest = max(reading.at for group in groups.values() for reading in group)
    history = []
    next_shift = []
    for room, group in groups.items():
        group.sort(key=lambda reading: reading.at)
        if len(group) < 18:
            raise ValueError(f"{room} 至少需要 18 个连续班次端点。")
        if group[-1].at != expected_latest:
            raise ValueError(f"{room} 缺少最近的交班端点，请补齐后重算。")
        for before, after in zip(group, group[1:]):
            gap = after.at - before.at
            if not gap:
                raise ValueError(f"{room} 的端点 {after.at:{TIME_FORMAT}} 重复。")
            if gap != SHIFT:
                raise ValueError(f"{room} 在 {before.at:{TIME_FORMAT}} 后缺交班读数，需保持 8 小时间隔。")
        history.extend(
            Example(ShiftInputs(issue, previous), actual.inside_rh)
            for previous, issue, actual in zip(group, group[1:], group[2:])
        )
        next_shift.append(ShiftInputs(group[-1], group[-2]))
    return sorted(history, key=lambda example: example.inputs.current.at), next_shift
