"""更换库房湿度计的双表同抄校准。

换表期间新旧两只表并行抄录若干班：
- 同一班次同一库房的双表读数只计一次（重复录入先去重）；
- 用前段同抄读数估计两表偏差（新表读数换算到旧表尺度）；
- 用末段同抄读数做独立核验，任一班残差超过两个百分点即判定失效；
- 留不出核验班次（同抄不足两班）或核验失败的库房转人工复测，不做自动更正。

校准成立后，换表时点起的新表读数按 ``新表 + 偏差`` 更正到旧表尺度，
保证跨表的湿度变化量与历史序列口径一致。
"""

from dataclasses import dataclass, field
from datetime import datetime
from statistics import fmean

# 单班核验允许的最大偏差残差（百分点）。
MAX_CHECK_RESIDUAL = 2.0
# 估计偏差与独立核验各自至少需要的同抄班次数。
MIN_FIT_SHIFTS = 1
MIN_CHECK_SHIFTS = 1
TIME_FORMAT = "%Y-%m-%d %H:%M"


@dataclass(frozen=True)
class ParallelReading:
    """同一班次新旧两表的一次同抄。"""

    room: str
    at: datetime
    old_rh: float
    new_rh: float

    @property
    def difference(self) -> float:
        """旧表读数减新表读数，即把新表读数平移到旧表尺度所需的偏差。"""
        return self.old_rh - self.new_rh


@dataclass
class RoomCalibration:
    room: str
    switched_at: datetime | None
    fit_shift_count: int
    check_shift_count: int
    paired_shift_count: int
    bias: float | None = None
    fit_residual_max: float | None = None
    check_residual_max: float | None = None
    valid: bool = False
    manual_recheck: bool = True
    reason: str = ""
    readings: list[ParallelReading] = field(default_factory=list)

    def to_record(self) -> dict:
        return {
            "room": self.room,
            "switched_at": self.switched_at.strftime(TIME_FORMAT) if self.switched_at else None,
            "valid": self.valid,
            "manual_recheck": self.manual_recheck,
            "bias": round(self.bias, 4) if self.bias is not None else None,
            "fit_shift_count": self.fit_shift_count,
            "check_shift_count": self.check_shift_count,
            "paired_shift_count": self.paired_shift_count,
            "fit_residual_max": round(self.fit_residual_max, 3) if self.fit_residual_max is not None else None,
            "check_residual_max": round(self.check_residual_max, 3) if self.check_residual_max is not None else None,
            "reason": self.reason,
            "readings": [
                {
                    "shift_at": item.at.strftime(TIME_FORMAT),
                    "old_rh": item.old_rh,
                    "new_rh": item.new_rh,
                    "difference": round(item.difference, 3),
                }
                for item in self.readings
            ],
        }


def _parse_shift(value) -> datetime:
    if isinstance(value, datetime):
        observed = value
    else:
        try:
            observed = datetime.strptime(str(value), TIME_FORMAT)
        except (ValueError, TypeError) as exc:
            raise ValueError("同抄班次时间应使用 YYYY-MM-DD HH:MM。") from exc
    if observed.hour not in (0, 8, 16) or observed.minute or observed.second:
        raise ValueError("同抄班次端点应为 00:00、08:00 或 16:00。")
    return observed


def _parse_rh(value, label) -> float:
    try:
        rh = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label}应为数字。") from exc
    if not 0.0 <= rh <= 100.0:
        raise ValueError(f"{label}应在 0 至 100 之间。")
    return rh


def group_readings(entries: list[dict]) -> dict[str, list[ParallelReading]]:
    """按库房归集同抄记录，并对同一班次的重复双表读数只计一次。"""
    grouped: dict[str, list[ParallelReading]] = {}
    for index, entry in enumerate(entries, start=1):
        room = str(entry.get("room", "")).strip()
        if not room:
            raise ValueError(f"第 {index} 条同抄记录缺少库房。")
        at = _parse_shift(entry.get("shift_at"))
        old_rh = _parse_rh(entry.get("old_rh"), f"{room} 同抄旧表湿度")
        new_rh = _parse_rh(entry.get("new_rh"), f"{room} 同抄新表湿度")
        grouped.setdefault(room, []).append(ParallelReading(room, at, old_rh, new_rh))

    deduped: dict[str, list[ParallelReading]] = {}
    for room, items in grouped.items():
        unique: dict[datetime, ParallelReading] = {}
        for item in items:
            # 同一班的双表读数只算一次：重复录入以首次为准，后续直接忽略。
            unique.setdefault(item.at, item)
        deduped[room] = sorted(unique.values(), key=lambda item: item.at)
    return deduped


def calibrate_room(room: str, readings: list[ParallelReading]) -> RoomCalibration:
    """前段估偏差、末段独立核验，决定该库房是否转人工复测。"""
    paired = len(readings)
    switched_at = readings[-1].at if readings else None
    base = RoomCalibration(
        room=room, switched_at=switched_at,
        fit_shift_count=0, check_shift_count=0, paired_shift_count=paired,
        readings=readings,
    )
    if paired < MIN_FIT_SHIFTS + MIN_CHECK_SHIFTS:
        base.reason = "同抄班次不足以同时留出估计段与核验班次，转人工复测。"
        return base

    # 末段至少留一班核验，其余前段用于估计偏差。
    check_count = max(MIN_CHECK_SHIFTS, paired // 4)
    fit = readings[:-check_count]
    check = readings[-check_count:]
    base.fit_shift_count = len(fit)
    base.check_shift_count = len(check)
    if len(fit) < MIN_FIT_SHIFTS:
        base.reason = "前段同抄读数不足以估计两表偏差，转人工复测。"
        return base

    bias = fmean(item.difference for item in fit)
    base.bias = bias
    base.fit_residual_max = max(abs(item.difference - bias) for item in fit)
    check_residuals = [abs(item.difference - bias) for item in check]
    base.check_residual_max = max(check_residuals)
    if base.check_residual_max > MAX_CHECK_RESIDUAL:
        base.reason = (
            f"末段核验有班次残差 {base.check_residual_max:.2f} 个百分点，"
            "超过两个百分点限值，转人工复测。"
        )
        return base

    base.valid = True
    base.manual_recheck = False
    base.reason = (
        f"前段 {len(fit)} 班估计偏差 {bias:.2f} 个百分点，"
        f"末段 {len(check)} 班核验通过（最大残差 {base.check_residual_max:.2f}）。"
    )
    return base


def build_calibrations(entries: list[dict]) -> list[RoomCalibration]:
    grouped = group_readings(entries)
    return [calibrate_room(room, grouped[room]) for room in sorted(grouped)]


def calibrate_rows(rows: list[dict], calibrations: list[RoomCalibration]) -> tuple[list[dict], set[str]]:
    """把换表时点起的新表读数更正到旧表尺度。

    同抄期内的行（其班次存在双表记录）保持原值，避免把用于校准的读数再次平移；
    待人工复测的库房不做更正。返回更正后的新行集合与被更正行数。
    """
    usable = {item.room: item for item in calibrations if item.valid}
    paired_points = {
        (item.room, item.at)
        for calibration in calibrations for item in calibration.readings
    }
    corrected: list[dict] = []
    changed_keys: set[str] = set()
    for row in rows:
        updated = dict(row)
        room = row.get("room")
        calibration = usable.get(room)
        if calibration is None or calibration.switched_at is None:
            corrected.append(updated)
            continue
        at = _parse_shift(row.get("shift_at"))
        if (room, at) in paired_points or at < calibration.switched_at:
            corrected.append(updated)
            continue
        original = _parse_rh(row.get("inside_rh"), f"{room} 库内湿度")
        updated["inside_rh"] = round(original + calibration.bias, 2)
        updated["calibration_bias"] = round(calibration.bias, 4)
        changed_keys.add(str(row.get("sample_id")))
        corrected.append(updated)
    return corrected, changed_keys


def recheck_rooms(calibrations: list[RoomCalibration]) -> list[str]:
    return sorted(item.room for item in calibrations if item.manual_recheck)
