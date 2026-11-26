import json

from sqlalchemy import func, select

from migrations.bootstrap import migrate
from src.business.demo import demo_calibration, demo_rows
from src.business.profile import PROFILE
from src.config.settings import Session, engine
from src.constants.workflow import Role
from src.models.account import Account
from src.models.calibration import Calibration
from src.models.dataset import Dataset
from src.services import calibrations
from src.services.datasets import save_in
from src.utils.csv_data import parse_csv, render_csv
from src.utils.passwords import hash_password

PASSWORD = "Yangfan-demo-2026"


def seed():
    columns = PROFILE["columns"]
    rows = parse_csv(render_csv(demo_rows(), [column["key"] for column in columns]), columns)
    with Session.begin() as db:
        for role in Role:
            email = f"{role.value}@demo.local"
            if db.get(Account, email) is None:
                db.add(Account(email=email, role=role.value, password_hash=hash_password(PASSWORD)))
        db.flush()
        item, created = save_in(db, PROFILE["seed_name"], rows, "seed", audit=False)
        if not db.scalar(select(Calibration).limit(1)):
            readings = demo_calibration("C01 票证盒架", bias=2.0, shifts=4) + \
                demo_calibration("C06 包装底片", manual=True)
            rooms = calibrations.build_calibrations(readings)
            manual = calibrations.recheck_rooms(rooms)
            db.add(Calibration(
                dataset_id=item.id, label="演示换表校准", readings=readings,
                result={
                    "summary": f"演示校准：{len(rooms) - len(manual)} 个核验通过，{len(manual)} 个转人工复测。",
                    "rooms": [room.to_record() for room in rooms],
                    "manual_recheck_rooms": manual,
                    "invalidated_runs": 0,
                },
                actor="seed", note="演示数据：C01 新表系统偏低 2 个百分点；C06 仅一班同抄，触发人工复测。",
            ))
        return {
            "accounts": db.scalar(select(func.count()).select_from(Account)),
            "datasets": db.scalar(select(func.count()).select_from(Dataset)),
            "calibrations": db.scalar(select(func.count()).select_from(Calibration)),
            "rows": len(item.rows), "checksum": item.checksum, "created": created,
        }


if __name__ == "__main__":
    migrate(engine)
    print(json.dumps(seed(), ensure_ascii=False))
