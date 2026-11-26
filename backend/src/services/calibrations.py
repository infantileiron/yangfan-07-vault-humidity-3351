from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import select

from src.business.calibration import (
    TIME_FORMAT,
    ParallelReading,
    RoomCalibration,
    build_calibrations,
    recheck_rooms,
)
from src.config.settings import Session
from src.models.calibration import Calibration
from src.models.run import Run
from src.schemas.resources import calibration_view
from src.services import datasets
from src.services.audit import record


def require(db, calibration_id):
    calibration = db.get(Calibration, calibration_id)
    if calibration is None:
        raise HTTPException(404, "校准记录不存在。")
    return calibration


def list_calibrations():
    with Session() as db:
        items = db.scalars(select(Calibration).order_by(Calibration.created_at.desc(), Calibration.id.desc()))
        return [calibration_view(item) for item in items]


def detail(calibration_id):
    with Session() as db:
        return calibration_view(require(db, calibration_id), include_readings=True)


def create(body, actor):
    with Session.begin() as db:
        datasets.require(db, body.dataset_id)
        entries = [item.model_dump() for item in body.readings]
        if not entries:
            raise HTTPException(422, "至少填写一条新旧表同抄读数。")
        try:
            rooms = build_calibrations(entries)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        manual = recheck_rooms(rooms)
        result = {
            "summary": (
                f"共 {len(rooms)} 个库房完成同抄校准，{len(rooms) - len(manual)} 个核验通过，"
                f"{len(manual)} 个转人工复测。"
            ),
            "rooms": [item.to_record() for item in rooms],
            "manual_recheck_rooms": manual,
        }
        calibration = Calibration(
            dataset_id=body.dataset_id, label=body.label,
            readings=entries, result=result, actor=actor, note=body.note,
        )
        db.add(calibration)
        db.flush()
        # 同数据集、口径已被本次校准改变的既有计算单（含待排班预测）标记失效，需重算。
        current_snapshot = snapshot_calibrations(db, body.dataset_id)
        affected = 0
        for run in db.scalars(select(Run).where(Run.dataset_id == body.dataset_id)):
            if is_run_stale(run, current_snapshot):
                run.calibration_stale = True
                affected += 1
        # 整体重新赋值以确保 SQLAlchemy 把 JSON 变更标记为脏并随事务提交。
        calibration.result = {**result, "invalidated_runs": affected}
        record(db, actor, "calibration_created", calibration.id)
        return calibration_view(calibration, include_readings=True)


def active_calibrations(db, dataset_id: str) -> list[Calibration]:
    """同一数据集按时间排序的全部校准记录；同一库房以最后一条为准。"""
    return list(db.scalars(
        select(Calibration)
        .where(Calibration.dataset_id == dataset_id)
        .order_by(Calibration.created_at, Calibration.id)
    ))


def latest_room_bias(db, dataset_id: str) -> dict[str, dict]:
    """每个库房当前生效的校准结论（同房多次换表取最新一条）。"""
    current: dict[str, dict] = {}
    for calibration in active_calibrations(db, dataset_id):
        for room in calibration.result["rooms"]:
            current[room["room"]] = room
    return current


def effective_room_calibrations(db, dataset_id: str) -> list[RoomCalibration]:
    """供执行器使用：按库房取最新一条持久化结论并重建为业务对象。

    多次换表时只采用每个库房最后一次校准，避免把不同时期的同抄读数
    重新混算；待人工复测的库房仍以 manual_recheck 状态原样保留。
    """
    result = []
    for room, conclusion in latest_room_bias(db, dataset_id).items():
        readings = [
            ParallelReading(
                room=room,
                at=datetime.strptime(item["shift_at"], TIME_FORMAT),
                old_rh=float(item["old_rh"]),
                new_rh=float(item["new_rh"]),
            )
            for item in conclusion.get("readings", [])
        ]
        switched_at = (
            datetime.strptime(conclusion["switched_at"], TIME_FORMAT)
            if conclusion.get("switched_at") else None
        )
        result.append(RoomCalibration(
            room=room,
            switched_at=switched_at,
            fit_shift_count=conclusion.get("fit_shift_count", 0),
            check_shift_count=conclusion.get("check_shift_count", 0),
            paired_shift_count=conclusion.get("paired_shift_count", len(readings)),
            bias=conclusion.get("bias"),
            fit_residual_max=conclusion.get("fit_residual_max"),
            check_residual_max=conclusion.get("check_residual_max"),
            valid=bool(conclusion["valid"]),
            manual_recheck=bool(conclusion["manual_recheck"]),
            reason=conclusion.get("reason", ""),
            readings=readings,
        ))
    return result


def snapshot_calibrations(db, dataset_id: str) -> list[dict]:
    """计算单提交时固化的校准快照，只保留影响排班口径的字段。"""
    return [
        {"calibration_id": item.id, "room": room["room"], "valid": room["valid"],
         "manual_recheck": room["manual_recheck"], "bias": room["bias"]}
        for item in active_calibrations(db, dataset_id)
        for room in item.result["rooms"]
    ]


def is_run_stale(run, current_snapshot: list[dict]) -> bool:
    """判断计算单是否被之后的校准作废。

    规则一：计算单从未携带校准快照，而当前已存在校准（旧口径预测未应用更正）；
    规则二：快照与当前生效校准在房、有效性或偏差上存在任一差异。
    """
    if not current_snapshot:
        return False
    previous = run.calibration_snapshot or []

    def key(snapshot):
        return {(item["calibration_id"], item["room"]):
                (item["valid"], item["manual_recheck"], item["bias"]) for item in snapshot}

    return key(previous) != key(current_snapshot)


def pending_recheck_rooms(db) -> list[dict]:
    """巡查页使用：跨全部校准聚合仍待人工复测的库房（按数据集分组）。"""
    grouped: dict[str, dict[str, dict]] = {}
    for calibration in db.scalars(select(Calibration).order_by(Calibration.created_at, Calibration.id)):
        for room in calibration.result["rooms"]:
            grouped.setdefault(calibration.dataset_id, {})[room["room"]] = room
    pending = []
    for dataset_id, rooms in grouped.items():
        for room, conclusion in rooms.items():
            if conclusion["manual_recheck"]:
                pending.append({
                    "dataset_id": dataset_id,
                    "room": room,
                    "reason": conclusion["reason"],
                    "switched_at": conclusion["switched_at"],
                })
    return pending
