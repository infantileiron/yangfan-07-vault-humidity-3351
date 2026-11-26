from datetime import datetime

from sqlalchemy import JSON, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, new_id, utcnow


class Calibration(Base):
    """一次换湿度计的双表同抄校准申请及其分房结论。"""

    __tablename__ = "calibrations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id"), index=True)
    label: Mapped[str] = mapped_column(String(100))
    readings: Mapped[list] = mapped_column(JSON)
    result: Mapped[dict] = mapped_column(JSON)
    actor: Mapped[str] = mapped_column(String(160))
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
