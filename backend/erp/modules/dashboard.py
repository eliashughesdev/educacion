from datetime import date

from fastapi import APIRouter, Depends

from erp.core.db import db
from erp.core.models import out
from erp.core.security import Ctx, require
from erp.shared.utils import today_iso, money, aging_bucket

router = APIRouter(prefix="/api/dashboard")


def last_months(n=12) -> list:
    d = date.today().replace(day=1)
    res = []
    for _ in range(n):
        res.append(d.strftime("%Y-%m"))
        d = (d.replace(day=1) - __import__("datetime").timedelta(days=1)).replace(day=1)
    return list(reversed(res))


async def group_sum(coll, match, key_expr, field):
    rows = await db[coll].aggregate([{"$match": match}, {"$group": {"_id": key_expr, "total": {"$sum": field}, "count": {"$sum": 1}}}]).to_list(500)
    return {r["_id"]: r for r in rows}


@router.get("/summary")
async def summary(ctx: Ctx = Depends(require("dashboard:view"))):
    s = ctx.scope()
    today = today_iso()
    year = await db.academic_years.find_one({**s, "is_current": True})
    year_q = {"academic_year_id": str(year["_id"])} if year else {}
    months = last_months()
    paid_match = {**s, "status": "aplicado", "paid_at": {"$gte": months[0]}}
    by_month = await group_sum("payments", paid_match, {"$substr": ["$paid_at", 0, 7]}, "$amount")
    billed = await group_sum("invoices", {**s, "status": {"$ne": "anulada"}, "issue_date": {"$gte": months[0]}}, {"$substr": ["$issue_date", 0, 7]}, "$total")
    by_method = await group_sum("payments", {**s, "status": "aplicado", "paid_at": {"$gte": today[:4]}}, "$method", "$amount")
    today_rev = await group_sum("payments", {**s, "status": "aplicado", "paid_at": {"$gte": today}}, None, "$amount")
    open_inv = await db.invoices.find({**s, "balance": {"$gt": 0.004}, "status": {"$ne": "anulada"}},
                                      {"due_date": 1, "balance": 1, "student_id": 1}).to_list(100000)
    buckets = {"corriente": 0.0, "1-30": 0.0, "31-60": 0.0, "61-90": 0.0, "90+": 0.0}
    morosos = set()
    for inv in open_inv:
        _, b = aging_bucket(inv["due_date"], today)
        buckets[b] += inv["balance"]
        if b != "corriente":
            morosos.add(inv["student_id"])
    sections = await db.sections.find({**s, **year_q}).sort("grade_order", 1).to_list(1000)
    cap = sum(x["capacity"] for x in sections) or 1
    enrolled = sum(x.get("enrolled_count", 0) for x in sections)
    by_grade = {}
    for x in sections:
        g = by_grade.setdefault(x["grade_name"], {"grade": x["grade_name"], "enrolled": 0, "capacity": 0})
        g["enrolled"] += x.get("enrolled_count", 0)
        g["capacity"] += x["capacity"]
    hot = sorted(sections, key=lambda x: x.get("enrolled_count", 0) / x["capacity"], reverse=True)[:6]
    overdue = sum(v for k, v in buckets.items() if k != "corriente")
    receivable = sum(buckets.values())
    this_month = today[:7]
    activity = await db.audit_logs.find(s).sort("at", -1).limit(8).to_list(8)
    return {
        "academic_year": year["name"] if year else None,
        "kpis": {
            "students_active": await db.students.count_documents({**s, "status": "activo"}),
            "prospects": await db.students.count_documents({**s, "status": "prospecto"}),
            "enrollments_active": await db.enrollments.count_documents({**s, **year_q, "status": "activa"}),
            "new_enrollments": await db.enrollments.count_documents({**s, **year_q, "type": "nueva"}),
            "withdrawals": await db.enrollments.count_documents({**s, **year_q, "status": "retirada"}),
            "occupancy": round(100 * enrolled / cap, 1), "capacity": cap, "enrolled": enrolled,
            "revenue_today": money(today_rev.get(None, {}).get("total", 0)),
            "revenue_month": money(by_month.get(this_month, {}).get("total", 0)),
            "revenue_year": money(sum(v["total"] for k, v in by_month.items() if k.startswith(today[:4]))),
            "billed_month": money(billed.get(this_month, {}).get("total", 0)),
            "receivable": money(receivable), "overdue": money(overdue), "morosos": len(morosos),
            "delinquency_rate": round(100 * overdue / receivable, 1) if receivable else 0,
            "open_cash_sessions": await db.cash_sessions.count_documents({**s, "status": "abierta"}),
        },
        "monthly": [{"month": m, "revenue": money(by_month.get(m, {}).get("total", 0)), "billed": money(billed.get(m, {}).get("total", 0))} for m in months],
        "by_method": [{"method": k, "total": money(v["total"]), "count": v["count"]} for k, v in by_method.items()],
        "aging": [{"bucket": k, "total": money(v)} for k, v in buckets.items()],
        "by_grade": list(by_grade.values()),
        "hot_sections": [{"id": str(x["_id"]), "name": f"{x['grade_name']} {x['name']}", "campus": x["campus_name"],
                          "enrolled": x.get("enrolled_count", 0), "capacity": x["capacity"]} for x in hot],
        "activity": [out(a) for a in activity],
        "formulas": {
            "occupancy": "Σ inscritos en secciones del año actual / Σ capacidad × 100",
            "delinquency_rate": "Saldo vencido (vencimiento < hoy) / saldo total por cobrar × 100",
            "morosos": "Estudiantes distintos con al menos una factura vencida con saldo",
            "revenue": "Σ pagos con estado 'aplicado' (excluye revertidos)",
        },
    }
