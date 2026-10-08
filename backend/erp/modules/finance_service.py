from bson import ObjectId
from fastapi import HTTPException, Request

from erp.core.audit import audit
from erp.core.db import db
from erp.core.models import out
from erp.shared.utils import now_iso, today_iso, to_oid, money, next_seq


async def invoice_number(institution_id: str) -> str:
    inst = await db.institutions.find_one({"_id": ObjectId(institution_id)})
    return f"{inst['code']}-F-{await next_seq('invoice:' + institution_id):06d}"


async def build_lines(institution_id: str, lines: list) -> list:
    result = []
    for ln in lines:
        qty = max(1, int(ln.get("quantity") or 1))
        if ln.get("fee_id"):
            fee = await db.fees.find_one({"_id": to_oid(ln["fee_id"]), "institution_id": institution_id, "status": "activo"})
            if not fee:
                raise HTTPException(422, "Tarifa inválida o inactiva")
            desc, price, category = ln.get("description") or fee["name"], fee["amount"], fee["category"]
        else:
            desc, price, category = ln.get("description"), float(ln.get("unit_price") or 0), "servicio"
            if not desc or price <= 0:
                raise HTTPException(422, "Cada línea manual requiere descripción y precio mayor que cero")
        gross = money(qty * price)
        discount = money(ln.get("discount") or 0)
        if discount < 0 or discount > gross:
            raise HTTPException(422, "El descuento no puede ser negativo ni mayor al importe de la línea")
        result.append({"fee_id": ln.get("fee_id"), "description": desc, "category": category, "quantity": qty,
                       "unit_price": money(price), "discount": discount, "total": money(gross - discount)})
    if not result:
        raise HTTPException(422, "La factura requiere al menos una línea")
    return result


async def create_invoice(ctx, student: dict, lines: list, due_date: str, notes: str, request: Request, batch_key: str = None,
                         issue_date: str = None) -> dict:
    inst_id = student["institution_id"]
    built = await build_lines(inst_id, lines)
    subtotal = money(sum(l["quantity"] * l["unit_price"] for l in built))
    discount = money(sum(l["discount"] for l in built))
    total = money(subtotal - discount)
    doc = {"institution_id": inst_id, "number": await invoice_number(inst_id), "student_id": str(student["_id"]),
           "student_name": student["full_name"], "student_code": student["code"], "grade_name": student.get("grade_name"),
           "issue_date": issue_date or today_iso(), "due_date": due_date, "lines": built, "subtotal": subtotal, "discount_total": discount,
           "total": total, "paid": 0.0, "balance": total, "status": "pendiente", "notes": notes, "batch_key": batch_key,
           "created_by": ctx.uid, "created_at": now_iso()}
    res = await db.invoices.insert_one(doc)
    await audit(ctx, "create", "invoices", res.inserted_id, {"number": doc["number"], "total": total}, ip=request.client.host if request else None)
    return out(await db.invoices.find_one({"_id": res.inserted_id}))
