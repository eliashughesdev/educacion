from datetime import datetime, timezone, date
from bson import ObjectId
from fastapi import HTTPException
from erp.core.db import db


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def today_iso() -> str:
    return date.today().isoformat()


def to_oid(value: str) -> ObjectId:
    if not ObjectId.is_valid(value):
        raise HTTPException(404, "Registro no encontrado")
    return ObjectId(value)


def money(v) -> float:
    return round(float(v) + 0.0, 2)


async def next_seq(name: str) -> int:
    doc = await db.counters.find_one_and_update({"_id": name}, {"$inc": {"seq": 1}}, upsert=True, return_document=True)
    return doc["seq"]


def invoice_status(paid: float, balance: float) -> str:
    if balance <= 0.004:
        return "pagada"
    return "parcial" if paid > 0 else "pendiente"


def aging_bucket(due_date: str, ref: str) -> tuple:
    days = (date.fromisoformat(ref) - date.fromisoformat(due_date[:10])).days
    if days <= 0:
        return 0, "corriente"
    if days <= 30:
        return days, "1-30"
    if days <= 60:
        return days, "31-60"
    if days <= 90:
        return days, "61-90"
    return days, "90+"
