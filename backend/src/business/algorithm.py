"""Rank the next shift's room humidity forecasts for manual staffing."""

from .calibration import RoomCalibration, calibrate_rows
from .rolling_backtest import bounded_predict, evaluate, fit_ridge
from .shift_series import TIME_FORMAT, form_series


def analyze(rows: list[dict], parameter: float, calibrations: list[RoomCalibration] | None = None) -> dict:
    if not 40 <= parameter <= 80:
        raise ValueError("湿度排班阈值应在 40% 至 80% 之间。")
    calibrations = calibrations or []
    corrected_rows, changed_keys = calibrate_rows(rows, calibrations)
    recheck = {item.room for item in calibrations if item.manual_recheck}
    history, next_shift = form_series(corrected_rows)
    model_mae, baseline_mae, cases, folds = evaluate(history)
    use_ridge = model_mae < baseline_mae

    if use_ridge:
        projections = bounded_predict(fit_ridge(history), next_shift)
        method = "滞后岭回归"
    else:
        projections = [item.current.inside_rh for item in next_shift]
        method = "沿用最新读数基线"

    result_rows = []
    for item, projection in zip(next_shift, projections):
        current = item.current
        expected = round(float(projection), 2)
        gap = round(expected - parameter, 2)
        manual = current.room in recheck
        if manual:
            disposition = "转人工复测"
        else:
            disposition = "优先除湿巡查" if gap >= 0 else "常规巡查"
        result_rows.append({
            "sample_id": current.sample_id,
            "room": current.room,
            "shift_at": item.target_at.strftime(TIME_FORMAT),
            "now_rh": current.inside_rh,
            "forecast_rh": expected,
            "threshold_gap": gap,
            "manual_recheck": manual,
            "calibrated": current.sample_id in changed_keys,
            "disposition": disposition,
        })
    result_rows.sort(key=lambda row: (-row["manual_recheck"], -row["forecast_rh"], row["room"]))
    urgent = sum(row["threshold_gap"] >= 0 and not row["manual_recheck"] for row in result_rows)
    recheck_count = len(recheck)
    corrected_count = len(changed_keys)

    summary = (
        f"滚动回测选用{method}。{len(result_rows)} 个库房中有 {urgent} 个达到下一班湿度巡查阈值。"
    )
    if corrected_count:
        summary += f"已按双表校准更正 {corrected_count} 条换表后读数。"
    if recheck_count:
        summary += f"{recheck_count} 个库房留待人工复测，未纳入自动优先排序。"

    metrics = [
        {"label": "滞后岭回归 MAE（百分点）", "value": round(model_mae, 3)},
        {"label": "最新读数基线 MAE（百分点）", "value": round(baseline_mae, 3)},
        {"label": "回测班段", "value": folds},
        {"label": "留出库房班次", "value": cases},
        {"label": "优先巡查库房", "value": urgent},
        {"label": "待人工复测库房", "value": recheck_count},
    ]
    notes = [
        "每段以首个留出班次作为发报时点，训练数据的实际湿度观测时间不晚于该时点。",
        "留出班次以单步滚动方式评估。后续班次可使用已到场的交班读数，训练系数在这一回测段内保持固定。",
        "沿用最新读数基线把交班湿度当作下一个交班端点预测。MAE 并列时使用基线。",
        "换表后的新表读数按同抄估计偏差平移到旧表尺度后再计算湿度变化与预测；同抄班次本身不重复更正。",
        "留不出核验班次或单班核验残差超过两个百分点的库房只标记人工复测，不做自动更正与优先排序。",
        "结果用于班长安排驻点巡查。实际设备操作由库房人员核查在场数据后决定。",
    ]
    return {
        "summary": summary,
        "metrics": metrics,
        "rows": result_rows,
        "notes": notes,
    }
