"""Rank the next shift's room humidity forecasts for manual staffing."""

from .rolling_backtest import bounded_predict, evaluate, fit_ridge
from .shift_series import TIME_FORMAT, form_series


def analyze(rows: list[dict], parameter: float) -> dict:
    if not 40 <= parameter <= 80:
        raise ValueError("湿度排班阈值应在 40% 至 80% 之间。")
    history, next_shift = form_series(rows)
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
        disposition = "优先除湿巡查" if gap >= 0 else "常规巡查"
        result_rows.append({
            "sample_id": current.sample_id,
            "room": current.room,
            "shift_at": item.target_at.strftime(TIME_FORMAT),
            "now_rh": current.inside_rh,
            "forecast_rh": expected,
            "threshold_gap": gap,
            "disposition": disposition,
        })
    result_rows.sort(key=lambda row: (-row["forecast_rh"], row["room"]))
    urgent = sum(row["threshold_gap"] >= 0 for row in result_rows)

    return {
        "summary": f"滚动回测选用{method}。{len(result_rows)} 个库房中有 {urgent} 个达到下一班湿度巡查阈值。",
        "metrics": [
            {"label": "滞后岭回归 MAE（百分点）", "value": round(model_mae, 3)},
            {"label": "最新读数基线 MAE（百分点）", "value": round(baseline_mae, 3)},
            {"label": "回测班段", "value": folds},
            {"label": "留出库房班次", "value": cases},
            {"label": "优先巡查库房", "value": urgent},
        ],
        "rows": result_rows,
        "notes": [
            "每段以首个留出班次作为发报时点，训练数据的实际湿度观测时间不晚于该时点。",
            "留出班次以单步滚动方式评估。后续班次可使用已到场的交班读数，训练系数在这一回测段内保持固定。",
            "沿用最新读数基线把交班湿度当作下一个交班端点预测。MAE 并列时使用基线。",
            "结果用于班长安排驻点巡查。实际设备操作由库房人员核查在场数据后决定。",
        ],
    }
