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
from erp.shared.exporters import export_response
from erp.shared.utils import now_iso, to_oid, money, next_seq, invoice_status

router = APIRouter(prefix="/api")
METHODS = Literal["efectivo", "tarjeta", "transferencia", "cheque", "deposito"]


class LineIn(BaseModel):
    fee_id: Optional[str] = None
    description: Optional[str] = None
    quantity: int = Field(default=1, ge=1, le=1000)
    unit_price: Optional[float] = Field(default=None, ge=0)
    discount: float = Field(default=0, ge=0)


class InvoiceIn(BaseModel):
    student_id: str
    due_date: date
    lines: List[LineIn] = Field(min_length=1)
    notes: Optional[str] = None


class BulkIn(BaseModel):
    fee_id: str
    period: str = Field(pattern=r"^\d{4}-\d{2}$")
    due_date: date
    grade_name: Optional[str] = None


class ReasonIn(BaseModel):
    reason: str = Field(min_length=5, max_length=300)


class OpenIn(BaseModel):
    register_name: str = Field(min_length=2, max_length=60)
    opening_amount: float = Field(ge=0)


class CloseIn(BaseModel):
    counted_amount: float = Field(ge=0)
    notes: Optional[str] = None


class PaymentIn(BaseModel):
    invoice_id: str
    amount: float = Field(gt=0)
    method: METHODS
    reference: Optional[str] = Field(default=None, max_length=80)
    idempotency_key: str = Field(min_length=8, max_length=80)


# ---------- Facturas ----------
@router.post("/invoices")
async def new_invoice(body: InvoiceIn, request: Request, ctx: Ctx = Depends(require("invoices:create"))):
    st = await db.students.find_one({"_id": to_oid(body.student_id)})
    check_institution(ctx, st)
    return await create_invoice(ctx, st, [l.model_dump() for l in body.lines], body.due_date.isoformat(), body.notes, request)


@router.post("/invoices/bulk-charges")
async def bulk_charges(body: BulkIn, request: Request, ctx: Ctx = Depends(require("invoices:bulk"))):
    inst = ctx.require_institution()
    fee = await db.fees.find_one({"_id": to_oid(body.fee_id), "institution_id": inst})
    if not fee:
        raise HTTPException(422, "Tarifa inválida")
    q = {"institution_id": inst, "status": "activo", "enrollment_id": {"$exists": True}}
    if body.grade_name:
        q["grade_name"] = body.grade_name
    students = await db.students.find(q).to_list(20000)
    key = f"{body.fee_id}:{body.period}"
    created, skipped = 0, 0
    for st in students:
        if await db.invoices.find_one({"student_id": str(st["_id"]), "batch_key": key, "status": {"$ne": "anulada"}}):
            skipped += 1
            continue
        await create_invoice(ctx, st, [{"fee_id": body.fee_id, "quantity": 1, "description": f"{fee['name']} {body.period}"}],
                             body.due_date.isoformat(), f"Cargo masivo {body.period}", request, batch_key=key)
        created += 1
    await audit(ctx, "bulk_charges", "invoices", None, {"fee": fee["code"], "period": body.period, "created": created, "skipped": skipped},
                ip=request.client.host)
    return {"created": created, "skipped": skipped}


@router.post("/invoices/{invoice_id}/void")
async def void_invoice(invoice_id: str, body: ReasonIn, request: Request, ctx: Ctx = Depends(require("invoices:void"))):
    inv = await db.invoices.find_one({"_id": to_oid(invoice_id)})
    check_institution(ctx, inv)
    res = await db.invoices.update_one({"_id": inv["_id"], "paid": {"$lte": 0}, "status": {"$ne": "anulada"}},
                                       {"$set": {"status": "anulada", "balance": 0.0, "void_reason": body.reason, "voided_at": now_iso(), "voided_by": ctx.uid}})
    if not res.modified_count:
        raise HTTPException(409, "Solo se pueden anular facturas sin pagos aplicados")
    await audit(ctx, "void", "invoices", inv["_id"], {"number": inv["number"], "reason": body.reason}, ip=request.client.host)
    return out(await db.invoices.find_one({"_id": inv["_id"]}))


async def _personal_check(ctx: Ctx, doc: dict):
    check_institution(ctx, doc)
    if ctx.student_ids is not None and doc.get("student_id") not in ctx.student_ids:
        raise HTTPException(404, "Registro no encontrado")


@router.get("/invoices/{invoice_id}/document")
async def invoice_document(invoice_id: str, request: Request, format: str = "pdf", ctx: Ctx = Depends(require("invoices:view"))):
    inv = await db.invoices.find_one({"_id": to_oid(invoice_id)})
    await _personal_check(ctx, inv)
    inst = await db.institutions.find_one({"_id": ObjectId(inv["institution_id"])})
    cols = [("description", "Concepto"), ("quantity", "Cant."), ("unit_price", "Precio"), ("discount", "Descuento"), ("total", "Importe")]
    meta = [("Institución", inst["name"]), ("RNC", inst.get("tax_id")), ("Factura", inv["number"]), ("Estudiante", f"{inv['student_name']} ({inv['student_code']})"),
            ("Emisión", inv["issue_date"]), ("Vencimiento", inv["due_date"]), ("Estado", inv["status"]),
            ("Nota", "Documento interno; no sustituye comprobante fiscal (NCF/e-CF)")]
    totals = [("Subtotal", inv["subtotal"]), ("Descuentos", inv["discount_total"]), ("Total", inv["total"]), ("Pagado", inv["paid"]), ("Saldo", inv["balance"])]
    await audit(ctx, "export", "invoices", inv["_id"], {"format": format}, ip=request.client.host)
    return export_response(format, f"factura-{inv['number']}", f"Factura {inv['number']}", cols, inv["lines"], meta, totals)


# ---------- Caja ----------
@router.get("/cash/current")
async def current_session(ctx: Ctx = Depends(require("cash:view"))):
    s = await db.cash_sessions.find_one({"cashier_id": ctx.uid, "status": "abierta"})
    return {"session": out(s) if s else None}


@router.post("/cash/open")
async def open_cash(body: OpenIn, request: Request, ctx: Ctx = Depends(require("cash:open"))):
    inst = ctx.require_institution()
    doc = {"institution_id": inst, "cashier_id": ctx.uid, "cashier_name": ctx.user["name"], "register_name": body.register_name,
           "opening_amount": money(body.opening_amount), "opened_at": now_iso(), "status": "abierta"}
    try:
        res = await db.cash_sessions.insert_one(doc)
    except DuplicateKeyError:
        raise HTTPException(409, "Ya tiene una caja abierta")
    await audit(ctx, "open", "cash_sessions", res.inserted_id, {"register": body.register_name, "opening": doc["opening_amount"]}, ip=request.client.host)
    return out(await db.cash_sessions.find_one({"_id": res.inserted_id}))


async def session_totals(session_id: str) -> dict:
    rows = await db.payments.aggregate([{"$match": {"session_id": session_id, "status": "aplicado"}},
                                        {"$group": {"_id": "$method", "total": {"$sum": "$amount"}, "count": {"$sum": 1}}}]).to_list(10)
    return {r["_id"]: {"total": money(r["total"]), "count": r["count"]} for r in rows}


@router.post("/cash/{session_id}/close")
async def close_cash(session_id: str, body: CloseIn, request: Request, ctx: Ctx = Depends(require("cash:close"))):
    s = await db.cash_sessions.find_one({"_id": to_oid(session_id)})
    check_institution(ctx, s)
    if s["cashier_id"] != ctx.uid and ctx.user["role"] not in ("superadmin", "admin_institucional"):
        raise HTTPException(403, "Solo el cajero responsable puede cerrar esta caja")
    totals = await session_totals(session_id)
    expected = money(s["opening_amount"] + totals.get("efectivo", {}).get("total", 0))
    upd = {"status": "cerrada", "closed_at": now_iso(), "closed_by": ctx.uid, "totals_by_method": totals, "expected_amount": expected,
           "counted_amount": money(body.counted_amount), "difference": money(body.counted_amount - expected), "close_notes": body.notes}
    res = await db.cash_sessions.update_one({"_id": s["_id"], "status": "abierta"}, {"$set": upd})
    if not res.modified_count:
        raise HTTPException(409, "La caja ya está cerrada")
    await audit(ctx, "close", "cash_sessions", s["_id"], {"expected": expected, "counted": upd["counted_amount"], "difference": upd["difference"]},
                ip=request.client.host)
    return out(await db.cash_sessions.find_one({"_id": s["_id"]}))


@router.get("/cash/{session_id}/report")
async def cash_report(session_id: str, request: Request, format: str = "pdf", ctx: Ctx = Depends(require("cash:export"))):
    s = await db.cash_sessions.find_one({"_id": to_oid(session_id)})
    check_institution(ctx, s)
    pays = [out(p) for p in await db.payments.find({"session_id": session_id}).sort("paid_at", 1).to_list(5000)]
    totals = s.get("totals_by_method") or await session_totals(session_id)
    cols = [("receipt_number", "Recibo"), ("paid_at", "Fecha"), ("student_name", "Estudiante"), ("invoice_number", "Factura"),
            ("method", "Método"), ("amount", "Monto"), ("status", "Estado")]
    meta = [("Caja", s["register_name"]), ("Cajero", s["cashier_name"]), ("Apertura", s["opened_at"]), ("Cierre", s.get("closed_at") or "Abierta"),
            ("Fondo inicial", s["opening_amount"])]
    tot = [(f"Total {m}", v["total"]) for m, v in totals.items()] + [("Esperado en efectivo", s.get("expected_amount")),
                                                                      ("Contado", s.get("counted_amount")), ("Diferencia", s.get("difference"))]
    await audit(ctx, "export", "cash_sessions", s["_id"], {"format": format}, ip=request.client.host)
    return export_response(format, f"arqueo-{s['register_name']}-{s['opened_at'][:10]}", "Arqueo y cierre de caja", cols, pays, meta, tot)


# ---------- Pagos ----------
@router.post("/payments")
async def register_payment(body: PaymentIn, request: Request, ctx: Ctx = Depends(require("payments:create"))):
    existing = await db.payments.find_one({"idempotency_key": body.idempotency_key})
    if existing:
        return {"payment": out(existing), "idempotent_replay": True}
    session = await db.cash_sessions.find_one({"cashier_id": ctx.uid, "status": "abierta"})
    if not session:
        raise HTTPException(409, "Debe abrir una caja antes de registrar pagos")
    inv = await db.invoices.find_one({"_id": to_oid(body.invoice_id)})
    check_institution(ctx, inv)
    amount = money(body.amount)
    if inv["status"] == "anulada" or amount > inv["balance"] + 0.004:
        raise HTTPException(409, f"Monto inválido. Saldo pendiente: {inv['balance']:,.2f}")
    inst = await db.institutions.find_one({"_id": ObjectId(inv["institution_id"])})
    doc = {"institution_id": inv["institution_id"], "invoice_id": body.invoice_id, "invoice_number": inv["number"], "student_id": inv["student_id"],
           "student_name": inv["student_name"], "student_code": inv["student_code"], "amount": amount, "method": body.method,
           "reference": body.reference, "session_id": str(session["_id"]), "cashier_id": ctx.uid, "cashier_name": ctx.user["name"],
           "idempotency_key": body.idempotency_key, "status": "procesando", "paid_at": now_iso()}
    try:
        res = await db.payments.insert_one(doc)
    except DuplicateKeyError:
        return {"payment": out(await db.payments.find_one({"idempotency_key": body.idempotency_key})), "idempotent_replay": True}
    upd = await db.invoices.find_one_and_update({"_id": inv["_id"], "status": {"$ne": "anulada"}, "balance": {"$gte": amount - 0.004}},
                                                {"$inc": {"paid": amount, "balance": -amount}}, return_document=True)
    if not upd:
        await db.payments.delete_one({"_id": res.inserted_id})
        raise HTTPException(409, "El saldo de la factura cambió; actualice e intente de nuevo")
    await db.invoices.update_one({"_id": inv["_id"]}, {"$set": {"status": invoice_status(upd["paid"], upd["balance"]),
                                                                "balance": money(max(upd["balance"], 0)), "paid": money(upd["paid"])}})
    receipt = f"{inst['code']}-R-{await next_seq('receipt:' + inv['institution_id']):06d}"
    await db.payments.update_one({"_id": res.inserted_id}, {"$set": {"status": "aplicado", "receipt_number": receipt}})
    await audit(ctx, "create", "payments", res.inserted_id, {"receipt": receipt, "invoice": inv["number"], "amount": amount, "method": body.method},
                ip=request.client.host)
    return {"payment": out(await db.payments.find_one({"_id": res.inserted_id})), "idempotent_replay": False}


@router.post("/payments/{payment_id}/reverse")
async def reverse_payment(payment_id: str, body: ReasonIn, request: Request, ctx: Ctx = Depends(require("payments:reverse"))):
    p = await db.payments.find_one({"_id": to_oid(payment_id)})
    check_institution(ctx, p)
    if p["cashier_id"] == ctx.uid:
        raise HTTPException(403, "Separación de funciones: no puede revertir un pago que usted registró")
    res = await db.payments.update_one({"_id": p["_id"], "status": "aplicado"},
                                       {"$set": {"status": "revertido", "reversed_at": now_iso(), "reversed_by": ctx.uid, "reverse_reason": body.reason}})
    if not res.modified_count:
        raise HTTPException(409, "El pago ya fue revertido o no está aplicado")
    upd = await db.invoices.find_one_and_update({"_id": ObjectId(p["invoice_id"])}, {"$inc": {"paid": -p["amount"], "balance": p["amount"]}},
                                                return_document=True)
    await db.invoices.update_one({"_id": upd["_id"]}, {"$set": {"status": invoice_status(upd["paid"], upd["balance"])}})
    await audit(ctx, "reverse", "payments", p["_id"], {"receipt": p.get("receipt_number"), "amount": p["amount"], "reason": body.reason},
                ip=request.client.host)
    return out(await db.payments.find_one({"_id": p["_id"]}))


@router.get("/payments/{payment_id}/receipt")
async def receipt(payment_id: str, request: Request, format: str = "pdf", ctx: Ctx = Depends(require("payments:view"))):
    p = await db.payments.find_one({"_id": to_oid(payment_id)})
    await _personal_check(ctx, p)
    inst = await db.institutions.find_one({"_id": ObjectId(p["institution_id"])})
    inv = await db.invoices.find_one({"_id": ObjectId(p["invoice_id"])})
    cols = [("description", "Concepto"), ("total", "Importe")]
    meta = [("Institución", inst["name"]), ("Recibo", p.get("receipt_number")), ("Fecha", p["paid_at"]), ("Estudiante", f"{p['student_name']} ({p['student_code']})"),
            ("Factura", p["invoice_number"]), ("Método", p["method"]), ("Referencia", p.get("reference") or "-"), ("Cajero", p["cashier_name"]),
            ("Estado", p["status"])]
    totals = [("Monto recibido", p["amount"]), ("Saldo restante de la factura", inv["balance"] if inv else None)]
    await audit(ctx, "export", "payments", p["_id"], {"format": format}, ip=request.client.host)
    return export_response(format, f"recibo-{p.get('receipt_number')}", f"Recibo de pago {p.get('receipt_number')}", cols, inv["lines"] if inv else [],
                           meta, totals)
