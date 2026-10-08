from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from erp.core.audit import audit
from erp.core.db import db
from erp.core.models import out
from erp.core.security import Ctx, get_ctx, require, check_institution
from erp.shared.exporters import export_response
from erp.shared.utils import to_oid, money

router = APIRouter(prefix="/api/students")


class GuardianLink(BaseModel):
    guardian_id: str


async def load_student(ctx: Ctx, student_id: str) -> dict:
    student_record = await db.students.find_one({"_id": to_oid(student_id)})
    check_institution(ctx, student_record)
    if ctx.student_ids is not None and student_id not in ctx.student_ids:
        raise HTTPException(404, "Registro no encontrado")
    if ctx.section_ids is not None and student_record.get("section_id") not in ctx.section_ids:
        raise HTTPException(404, "Registro no encontrado")
    return out(student_record)


@router.get("/{student_id}/detail")
async def detail(student_id: str, ctx: Ctx = Depends(require("students:view"))):
    st = await load_student(ctx, student_id)
    guardians = await db.guardians.find({"student_ids": student_id}).to_list(20)
    enrollments = await db.enrollments.find({"student_id": student_id}).sort("enrolled_at", -1).to_list(50)
    invoices = await db.invoices.find({"student_id": student_id}).sort("issue_date", -1).to_list(500)
    payments = await db.payments.find({"student_id": student_id}).sort("paid_at", -1).to_list(500)
    active = [i for i in invoices if i["status"] != "anulada"]
    return {
        "student": st,
        "guardians": [out(g) for g in guardians] if "guardians:view" in ctx.perms or ctx.student_ids is not None else [],
        "enrollments": [out(e) for e in enrollments],
        "invoices": [out(i) for i in invoices] if "invoices:view" in ctx.perms else [],
        "payments": [out(p) for p in payments] if "payments:view" in ctx.perms else [],
        "summary": {"billed": money(sum(i["total"] for i in active)), "paid": money(sum(i["paid"] for i in active)),
                    "balance": money(sum(i["balance"] for i in active))},
    }


@router.get("/{student_id}/statement")
async def statement(student_id: str, request: Request, format: str = "pdf", ctx: Ctx = Depends(require("invoices:view"))):
    st = await load_student(ctx, student_id)
    invoices = await db.invoices.find({"student_id": student_id, "status": {"$ne": "anulada"}}).sort("issue_date", 1).to_list(1000)
    rows = [out(i) for i in invoices]
    cols = [("number", "Factura"), ("issue_date", "Emisión"), ("due_date", "Vencimiento"), ("description", "Concepto"),
            ("total", "Total"), ("paid", "Pagado"), ("balance", "Saldo"), ("status", "Estado")]
    for r in rows:
        r["description"] = ", ".join(l["description"] for l in r.get("lines", []))
    totals = [("Total facturado", money(sum(r["total"] for r in rows))), ("Total pagado", money(sum(r["paid"] for r in rows))),
              ("Saldo pendiente", money(sum(r["balance"] for r in rows)))]
    meta = [("Estudiante", st["full_name"]), ("Matrícula", st["code"]), ("Grado", f"{st.get('grade_name', '-')} {st.get('section_name', '')}")]
    await audit(ctx, "export", "student_statement", student_id, {"format": format}, ip=request.client.host)
    return export_response(format, f"estado-cuenta-{st['code']}", "Estado de cuenta", cols, rows, meta, totals)


@router.post("/{student_id}/guardians")
async def link_guardian(student_id: str, body: GuardianLink, request: Request, ctx: Ctx = Depends(require("students:update"))):
    st = await load_student(ctx, student_id)
    g = await db.guardians.find_one({"_id": to_oid(body.guardian_id)})
    check_institution(ctx, g)
    if g.get("institution_id") != st["institution_id"]:
        raise HTTPException(422, "El tutor pertenece a otra institución")
    await db.guardians.update_one({"_id": g["_id"]}, {"$addToSet": {"student_ids": student_id}})
    await db.students.update_one({"_id": ObjectId(st["id"])}, {"$addToSet": {"guardian_ids": body.guardian_id}})
    await audit(ctx, "link_guardian", "students", student_id, {"guardian_id": body.guardian_id}, ip=request.client.host)
    return {"ok": True}


@router.delete("/{student_id}/guardians/{guardian_id}")
async def unlink_guardian(student_id: str, guardian_id: str, request: Request, ctx: Ctx = Depends(require("students:update"))):
    st = await load_student(ctx, student_id)
    await db.guardians.update_one({"_id": to_oid(guardian_id), "institution_id": st["institution_id"]}, {"$pull": {"student_ids": student_id}})
    await db.students.update_one({"_id": ObjectId(st["id"])}, {"$pull": {"guardian_ids": guardian_id}})
    await audit(ctx, "unlink_guardian", "students", student_id, {"guardian_id": guardian_id}, ip=request.client.host)
    return {"ok": True}
