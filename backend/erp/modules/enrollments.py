from datetime import date
from typing import List, Literal, Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from pymongo.errors import DuplicateKeyError

from erp.core.audit import audit
from erp.core.db import db
from erp.core.models import out
from erp.core.security import Ctx, require, check_institution
from erp.modules.finance_service import create_invoice
from erp.shared.utils import now_iso, to_oid

router = APIRouter(prefix="/api/enrollments")


class EnrollIn(BaseModel):
    student_id: str
    section_id: str
    type: Literal["nueva", "reinscripcion", "traslado_externo"] = "nueva"
    fee_ids: List[str] = []
    due_date: Optional[date] = None


class ReasonIn(BaseModel):
    reason: str = Field(min_length=5, max_length=300)


class TransferIn(ReasonIn):
    section_id: str


async def reserve_seat(section_id: str):
    sec = await db.sections.find_one_and_update(
        {"_id": to_oid(section_id), "$expr": {"$lt": ["$enrolled_count", "$capacity"]}},
        {"$inc": {"enrolled_count": 1}}, return_document=True)
    if not sec:
        raise HTTPException(409, "La sección no tiene cupos disponibles")
    return sec


async def release_seat(section_id: str):
    await db.sections.update_one({"_id": to_oid(section_id), "enrolled_count": {"$gt": 0}}, {"$inc": {"enrolled_count": -1}})


def placement(sec: dict) -> dict:
    return {"section_id": str(sec["_id"]), "section_name": sec["name"], "grade_name": sec["grade_name"], "grade_id": sec["grade_id"],
            "campus_id": sec["campus_id"], "campus_name": sec["campus_name"], "academic_year_id": sec["academic_year_id"], "year_name": sec["year_name"]}


@router.post("")
async def enroll(body: EnrollIn, request: Request, ctx: Ctx = Depends(require("enrollments:create"))):
    st = await db.students.find_one({"_id": to_oid(body.student_id)})
    check_institution(ctx, st)
    sec = await db.sections.find_one({"_id": to_oid(body.section_id)})
    check_institution(ctx, sec)
    if sec["institution_id"] != st["institution_id"]:
        raise HTTPException(422, "Estudiante y sección pertenecen a instituciones distintas")
    if st["status"] in ("retirado", "egresado"):
        raise HTTPException(409, f"El estudiante está {st['status']}; reactívelo antes de matricular")
    if await db.enrollments.find_one({"student_id": body.student_id, "academic_year_id": sec["academic_year_id"], "status": "activa"}):
        raise HTTPException(409, "El estudiante ya tiene una matrícula activa en este año académico")
    sec = await reserve_seat(body.section_id)
    doc = {"institution_id": st["institution_id"], "student_id": body.student_id, "student_name": st["full_name"], "student_code": st["code"],
           **placement(sec), "type": body.type, "status": "activa", "enrolled_at": now_iso(), "created_by": ctx.uid}
    try:
        res = await db.enrollments.insert_one(doc)
    except DuplicateKeyError:
        await release_seat(body.section_id)
        raise HTTPException(409, "El estudiante ya tiene una matrícula activa en este año académico")
    await db.students.update_one({"_id": st["_id"]}, {"$set": {"status": "activo", **placement(sec), "enrollment_id": str(res.inserted_id)}})
    invoice = None
    if body.fee_ids:
        lines = [{"fee_id": f, "quantity": 1, "discount": 0} for f in body.fee_ids]
        invoice = await create_invoice(ctx, st, lines, (body.due_date or date.today()).isoformat(), "Cargos de matrícula", request)
    await audit(ctx, "enroll", "enrollments", res.inserted_id, {"student": st["code"], "section": f"{sec['grade_name']} {sec['name']}"},
                ip=request.client.host)
    return {"enrollment": out(await db.enrollments.find_one({"_id": res.inserted_id})), "invoice": invoice}


async def _load(ctx: Ctx, enrollment_id: str) -> dict:
    enr = await db.enrollments.find_one({"_id": to_oid(enrollment_id)})
    check_institution(ctx, enr)
    if enr["status"] != "activa":
        raise HTTPException(409, "Solo se pueden modificar matrículas activas")
    return enr


@router.post("/{enrollment_id}/withdraw")
async def withdraw(enrollment_id: str, body: ReasonIn, request: Request, ctx: Ctx = Depends(require("enrollments:withdraw"))):
    enr = await _load(ctx, enrollment_id)
    res = await db.enrollments.update_one({"_id": enr["_id"], "status": "activa"},
                                          {"$set": {"status": "retirada", "withdrawn_at": now_iso(), "withdraw_reason": body.reason}})
    if res.modified_count:
        await release_seat(enr["section_id"])
        await db.students.update_one({"_id": ObjectId(enr["student_id"])}, {"$set": {"status": "retirado"}})
    await audit(ctx, "withdraw", "enrollments", enr["_id"], {"reason": body.reason}, ip=request.client.host)
    return out(await db.enrollments.find_one({"_id": enr["_id"]}))


@router.post("/{enrollment_id}/transfer")
async def transfer(enrollment_id: str, body: TransferIn, request: Request, ctx: Ctx = Depends(require("enrollments:update"))):
    enr = await _load(ctx, enrollment_id)
    target = await db.sections.find_one({"_id": to_oid(body.section_id)})
    check_institution(ctx, target)
    if target["academic_year_id"] != enr["academic_year_id"] or str(target["_id"]) == enr["section_id"]:
        raise HTTPException(422, "La sección destino debe ser distinta y del mismo año académico")
    target = await reserve_seat(body.section_id)
    await release_seat(enr["section_id"])
    await db.enrollments.update_one({"_id": enr["_id"]}, {"$set": {"status": "trasladada", "transferred_at": now_iso(), "transfer_reason": body.reason}})
    new = {**{k: v for k, v in enr.items() if k != "_id"}, **placement(target), "type": "cambio_seccion", "status": "activa",
           "enrolled_at": now_iso(), "previous_enrollment_id": enrollment_id, "created_by": ctx.uid}
    res = await db.enrollments.insert_one(new)
    await db.students.update_one({"_id": ObjectId(enr["student_id"])}, {"$set": {**placement(target), "enrollment_id": str(res.inserted_id)}})
    await audit(ctx, "transfer", "enrollments", res.inserted_id,
                {"from": enr["section_name"], "to": target["name"], "reason": body.reason}, ip=request.client.host)
    return out(await db.enrollments.find_one({"_id": res.inserted_id}))
