"""Expanding-origin comparison against the last observed room humidity."""

import numpy as np
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from .shift_series import Example, ShiftInputs


def fit_ridge(examples: list[Example]):
    model = make_pipeline(StandardScaler(), Ridge(alpha=2.0))
    model.fit([example.inputs.features for example in examples],
              [example.actual_rh for example in examples])
    return model


def bounded_predict(model, inputs: list[ShiftInputs]) -> np.ndarray:
    return np.clip(model.predict([item.features for item in inputs]), 0, 100)


def evaluate(history: list[Example]) -> tuple[float, float, int, int]:
    issue_times = sorted({example.inputs.current.at for example in history})
    cutoff = max(8, len(issue_times) // 2)
    boundaries = [
        issue_times[index] for index in range(cutoff, len(issue_times), 3)
    ]
    if len(boundaries) < 3:
        raise ValueError("滚动回测至少需要三段留出班次，请提交更多连续读数。")

    model_errors = []
    persistence_errors = []
    for fold, start in enumerate(boundaries):
        end = boundaries[fold + 1] if fold + 1 < len(boundaries) else None
        train = [example for example in history if example.inputs.target_at <= start]
        validation = [
            example for example in history
            if example.inputs.current.at >= start and (end is None or example.inputs.current.at < end)
        ]
        prediction = bounded_predict(fit_ridge(train), [example.inputs for example in validation])
        for example, forecast in zip(validation, prediction):
            model_errors.append(abs(example.actual_rh - forecast))
            persistence_errors.append(abs(example.actual_rh - example.inputs.current.inside_rh))

    return (
        float(np.mean(model_errors)), float(np.mean(persistence_errors)),
        len(model_errors), len(boundaries),
    )
