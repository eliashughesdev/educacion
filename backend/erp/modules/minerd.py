import hashlib
import json
from typing import Dict, List, Literal, Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

from erp.core.audit import audit
from erp.core.db import db
from erp.core.models import out
from erp.core.security import Ctx, require, check_institution
from erp.modules.minerd_templates import pick_template
from erp.shared.exporters import export_response
from erp.shared.report_card_pdf import build_report_cards_pdf
from erp.shared.utils import now_iso, today_iso, to_oid

router = APIRouter(prefix="/api")
Period = Literal["P1", "P2", "P3", "P4"]


class GradeRow(BaseModel):
    student_id: str
    scores: Dict[str, Optional[str | float]]


class GradebookIn(BaseModel):
    section_id: str
    subject_id: str
    period: Period
    rows: List[GradeRow]


class PublishIn(BaseModel):
    section_id: str
    subject_id: str
    period: Period


class NoteRow(BaseModel):
    student_id: str
    present: Optional[int] = Field(default=None, ge=0, le=200)
    absent: Optional[int] = Field(default=None, ge=0, le=200)
    observation: Optional[str] = Field(default=None, max_length=1200)
    support: Optional[str] = Field(default=None, max_length=1200)


class NotesIn(BaseModel):
    section_id: str
    period: Period
    rows: List[NoteRow]


class RevisionIn(PublishIn):
    student_id: str
    scores: Dict[str, Optional[str | float]]
    reason: str = Field(min_length=10, max_length=400)


class ResolveIn(BaseModel):
    approve: bool
    comment: Optional[str] = None


class ApproveIn(BaseModel):
    stage: Literal["docente", "direccion"]


async def templates():
    return await db.report_card_templates.find({}, {"_id": 0}).to_list(50)


async def section_ctx(ctx: Ctx, section_id: str):
    sec = await db.sections.find_one({"_id": to_oid(section_id)})
    check_institution(ctx, sec)
    if ctx.section_ids is not None and section_id not in ctx.section_ids:
        raise HTTPException(404, "Sección no asignada a este docente")
    tpl = pick_template(await templates(), sec.get("level"), sec.get("grade_order"))
    if not tpl:
        raise HTTPException(422, "No hay plantilla de evaluación configurada para este nivel/grado")
    return sec, tpl


async def editable(ctx: Ctx, section_id: str, subject_id: str) -> bool:
    if "gradebook:edit" not in ctx.perms:
        return False
    if ctx.user["role"] != "docente":
        return True
    mine = [a for a in ctx.assignments if a["section_id"] == section_id]
    if any(a.get("subject_id") == subject_id and a["role"] in ("asignatura", "sustituto") for a in mine):
        return True
    taken = await db.teacher_assignments.find_one({"section_id": section_id, "subject_id": subject_id, "status": "activa", "role": "asignatura"})
    return any(a["role"] == "titular" for a in mine) and not taken


def is_titular(ctx: Ctx, section_id: str) -> bool:
    return ctx.user["role"] != "docente" or any(a["section_id"] == section_id and a["role"] == "titular" for a in ctx.assignments)


def clean_scores(tpl: dict, scores: dict) -> dict:
    keys = {c["key"] for c in tpl["competencies"]}
    res = {}
    for k, v in scores.items():
        if k not in keys:
            raise HTTPException(422, f"Competencia no válida: {k}")
        if v in (None, ""):
            continue
        if tpl["scale_type"] == "numeric":
            try:
                v = float(v)
            except (TypeError, ValueError):
                raise HTTPException(422, f"Valor no numérico en {k}")
            if not tpl["min"] <= v <= tpl["max"]:
                raise HTTPException(422, f"Nota fuera de escala ({tpl['min']}-{tpl['max']}) en {k}: {v}")
        elif v not in {x["key"] for x in tpl["values"]}:
            raise HTTPException(422, f"Valor cualitativo no válido en {k}: {v}")
        res[k] = v
    return res


async def roster(section_id: str):
    enr = await db.enrollments.find({"section_id": section_id, "status": "activa"}).sort("student_name", 1).to_list(200)
    return [{"student_id": e["student_id"], "student_name": e["student_name"], "student_code": e["student_code"]} for e in enr]


@router.get("/minerd/templates")
async def list_templates(ctx: Ctx = Depends(require("gradebook:view"))):
    return await templates()


@router.get("/minerd/my-sections")
async def my_sections(ctx: Ctx = Depends(require("gradebook:view"))):
    year = await db.academic_years.find_one({**ctx.scope(), "is_current": True})
    q = {**ctx.scope(), "academic_year_id": str(year["_id"]) if year else None}
    if ctx.section_ids is not None:
        q["_id"] = {"$in": [ObjectId(i) for i in ctx.section_ids]}
    secs = await db.sections.find(q).sort("grade_order", 1).to_list(500)
    res = []
    for s in secs:
        sid = str(s["_id"])
        subs = await db.subjects.find({"institution_id": s["institution_id"], "status": "activo", "levels": {"$regex": s.get("level") or "-"}}).sort("order", 1).to_list(30)
        res.append({"section_id": sid, "label": f"{s['grade_name']} {s['name']}", "campus": s["campus_name"], "is_titular": is_titular(ctx, sid),
                    "subjects": [{"id": str(x["_id"]), "name": x["name"], "editable": await editable(ctx, sid, str(x["_id"]))} for x in subs]})
    return res


@router.get("/gradebook")
async def get_gradebook(section_id: str, subject_id: str, period: Period, ctx: Ctx = Depends(require("gradebook:view"))):
    sec, tpl = await section_ctx(ctx, section_id)
    state = await db.grade_periods.find_one({"section_id": section_id, "subject_id": subject_id, "period": period})
    grades = {g["student_id"]: g["scores"] for g in await db.competency_grades.find({"section_id": section_id, "subject_id": subject_id, "period": period}).to_list(300)}
    rows = [{**r, "scores": grades.get(r["student_id"], {})} for r in await roster(section_id)]
    status = state["status"] if state else "borrador"
    return {"template": tpl, "status": status, "can_edit": status != "publicado" and await editable(ctx, section_id, subject_id), "rows": rows}


@router.put("/gradebook")
async def save_gradebook(body: GradebookIn, request: Request, ctx: Ctx = Depends(require("gradebook:edit"))):
    sec, tpl = await section_ctx(ctx, body.section_id)
    if not await editable(ctx, body.section_id, body.subject_id):
        raise HTTPException(403, "No tiene asignada esta asignatura en la sección")
    state = await db.grade_periods.find_one({"section_id": body.section_id, "subject_id": body.subject_id, "period": body.period})
    if state and state["status"] == "publicado":
        raise HTTPException(409, "Período publicado y bloqueado. Use una solicitud de corrección.")
    valid = {r["student_id"] for r in await roster(body.section_id)}
    for row in body.rows:
        if row.student_id not in valid:
            raise HTTPException(422, "Estudiante no pertenece a la sección")
        scores = clean_scores(tpl, row.scores)
        await db.competency_grades.update_one(
            {"student_id": row.student_id, "section_id": body.section_id, "subject_id": body.subject_id, "period": body.period},
            {"$set": {"scores": scores, "institution_id": sec["institution_id"], "academic_year_id": sec["academic_year_id"],
                      "updated_by": ctx.uid, "updated_at": now_iso()}}, upsert=True)
    await db.grade_periods.update_one({"section_id": body.section_id, "subject_id": body.subject_id, "period": body.period},
                                      {"$setOnInsert": {"status": "borrador", "institution_id": sec["institution_id"]}}, upsert=True)
    await audit(ctx, "save_grades", "gradebook", body.section_id, {"subject": body.subject_id, "period": body.period, "rows": len(body.rows)},
                ip=request.client.host)
    return {"ok": True, "saved": len(body.rows)}


@router.post("/gradebook/publish")
async def publish(body: PublishIn, request: Request, ctx: Ctx = Depends(require("gradebook:publish"))):
    sec, tpl = await section_ctx(ctx, body.section_id)
    if not await editable(ctx, body.section_id, body.subject_id):
        raise HTTPException(403, "No tiene asignada esta asignatura en la sección")
    grades = {g["student_id"]: g["scores"] for g in await db.competency_grades.find(
        {"section_id": body.section_id, "subject_id": body.subject_id, "period": body.period}).to_list(300)}
    keys = [c["key"] for c in tpl["competencies"]]
    missing = [r["student_name"] for r in await roster(body.section_id) if any(k not in grades.get(r["student_id"], {}) for k in keys)]
    if missing:
        raise HTTPException(422, f"Registros incompletos ({len(missing)}): {', '.join(missing[:6])}{'...' if len(missing) > 6 else ''}")
    res = await db.grade_periods.update_one({"section_id": body.section_id, "subject_id": body.subject_id, "period": body.period, "status": {"$ne": "publicado"}},
                                            {"$set": {"status": "publicado", "published_by": ctx.uid, "published_at": now_iso()}})
    if not res.modified_count:
        raise HTTPException(409, "El período ya estaba publicado o no tiene registros")
    await audit(ctx, "publish_grades", "gradebook", body.section_id, {"subject": body.subject_id, "period": body.period}, ip=request.client.host)
    return {"ok": True}


@router.get("/gradebook/period-notes")
async def get_notes(section_id: str, period: Period, ctx: Ctx = Depends(require("gradebook:view"))):
    await section_ctx(ctx, section_id)
    notes = {n["student_id"]: n for n in await db.period_notes.find({"section_id": section_id, "period": period}).to_list(300)}
    rows = [{**r, **{k: notes.get(r["student_id"], {}).get(k) for k in ("present", "absent", "observation", "support")}} for r in await roster(section_id)]
    return {"can_edit": "gradebook:edit" in ctx.perms and is_titular(ctx, section_id), "rows": rows}


@router.put("/gradebook/period-notes")
async def save_notes(body: NotesIn, request: Request, ctx: Ctx = Depends(require("gradebook:edit"))):
    sec, _ = await section_ctx(ctx, body.section_id)
    if not is_titular(ctx, body.section_id):
        raise HTTPException(403, "Solo el maestro titular registra asistencia y observaciones del período")
    valid = {r["student_id"] for r in await roster(body.section_id)}
    for r in body.rows:
        if r.student_id not in valid:
            raise HTTPException(422, "Estudiante no pertenece a la sección")
        await db.period_notes.update_one({"student_id": r.student_id, "section_id": body.section_id, "period": body.period},
                                         {"$set": {**r.model_dump(exclude={"student_id"}), "academic_year_id": sec["academic_year_id"],
                                                   "institution_id": sec["institution_id"], "updated_by": ctx.uid, "updated_at": now_iso()}}, upsert=True)
    await audit(ctx, "save_period_notes", "gradebook", body.section_id, {"period": body.period}, ip=request.client.host)
    return {"ok": True}


@router.post("/grade-revisions")
async def request_revision(body: RevisionIn, request: Request, ctx: Ctx = Depends(require("gradebook:edit"))):
    sec, tpl = await section_ctx(ctx, body.section_id)
    if not await editable(ctx, body.section_id, body.subject_id):
        raise HTTPException(403, "No tiene asignada esta asignatura en la sección")
    g = await db.competency_grades.find_one({"student_id": body.student_id, "section_id": body.section_id, "subject_id": body.subject_id, "period": body.period})
    st = await db.students.find_one({"_id": to_oid(body.student_id)})
    sub = await db.subjects.find_one({"_id": to_oid(body.subject_id)})
    doc = {"institution_id": sec["institution_id"], "section_id": body.section_id, "subject_id": body.subject_id, "subject_name": sub["name"],
           "student_id": body.student_id, "student_name": st["full_name"], "period": body.period, "old_scores": (g or {}).get("scores", {}),
           "new_scores": clean_scores(tpl, body.scores), "reason": body.reason, "status": "pendiente", "requested_by": ctx.uid,
           "requested_by_email": ctx.user["email"], "created_at": now_iso()}
    res = await db.grade_revisions.insert_one(doc)
    await audit(ctx, "request_revision", "gradebook", res.inserted_id, {"student": st["code"], "period": body.period}, ip=request.client.host)
    return out(await db.grade_revisions.find_one({"_id": res.inserted_id}))


@router.post("/grade-revisions/{rev_id}/resolve")
async def resolve_revision(rev_id: str, body: ResolveIn, request: Request, ctx: Ctx = Depends(require("gradebook:approve_revision"))):
    rev = await db.grade_revisions.find_one({"_id": to_oid(rev_id)})
    check_institution(ctx, rev)
    if rev["requested_by"] == ctx.uid:
        raise HTTPException(403, "Separación de funciones: no puede aprobar su propia solicitud")
    res = await db.grade_revisions.update_one({"_id": rev["_id"], "status": "pendiente"}, {"$set": {
        "status": "aprobada" if body.approve else "rechazada", "resolved_by": ctx.uid, "resolved_at": now_iso(), "comment": body.comment}})
    if not res.modified_count:
        raise HTTPException(409, "La solicitud ya fue resuelta")
    if body.approve:
        await db.competency_grades.update_one({"student_id": rev["student_id"], "section_id": rev["section_id"], "subject_id": rev["subject_id"], "period": rev["period"]},
                                              {"$set": {"scores": {**rev["old_scores"], **rev["new_scores"]}, "updated_by": ctx.uid, "updated_at": now_iso(),
                                                        "revision_id": rev_id}}, upsert=True)
    await audit(ctx, "resolve_revision", "gradebook", rev["_id"], {"approved": body.approve, "before": rev["old_scores"], "after": rev["new_scores"]},
                ip=request.client.host)
    return {"ok": True}


# ---------- Boletín ----------
def _avg(vals):
    nums = [float(v) for v in vals if isinstance(v, (int, float))]
    return round(sum(nums) / len(nums)) if nums else None


async def compile_card(ctx: Ctx, student_id: str) -> dict:
    st = await db.students.find_one({"_id": to_oid(student_id)})
    check_institution(ctx, st)
    if ctx.student_ids is not None and student_id not in ctx.student_ids:
        raise HTTPException(404, "Registro no encontrado")
    if ctx.section_ids is not None and st.get("section_id") not in ctx.section_ids:
        raise HTTPException(404, "Registro no encontrado")
    if not st.get("section_id"):
        raise HTTPException(409, "El estudiante no tiene matrícula activa en una sección")
    sec = await db.sections.find_one({"_id": ObjectId(st["section_id"])})
    tpl = pick_template(await templates(), sec.get("level"), sec.get("grade_order"))
    inst = await db.institutions.find_one({"_id": ObjectId(st["institution_id"])})
    year_id = sec["academic_year_id"]
    subjects = await db.subjects.find({"institution_id": st["institution_id"], "status": "activo", "levels": {"$regex": sec.get("level") or "-"}}).sort("order", 1).to_list(30)
    grades = await db.competency_grades.find({"student_id": student_id, "academic_year_id": year_id}).to_list(500)
    published = {(g["subject_id"], g["period"]) for g in await db.grade_periods.find({"section_id": st["section_id"], "status": "publicado"}).to_list(500)}
    terms = await db.terms.find({"academic_year_id": year_id}).sort("start_date", 1).to_list(10)
    evaluable = [f"P{i + 1}" for i, t in enumerate(terms) if t["start_date"] <= today_iso()]
    comps, periods = [c["key"] for c in tpl["competencies"]], [p["key"] for p in tpl["periods"]]
    numeric = tpl["scale_type"] == "numeric"
    grid, issues = [], []
    for sub in subjects:
        sid = str(sub["_id"])
        row = {"subject": sub["name"], "periods": {c: {} for c in comps}, "finals": {}}
        for g in grades:
            if g["subject_id"] == sid and (sid, g["period"]) in published:
                for c, v in g["scores"].items():
                    row["periods"].setdefault(c, {})[g["period"]] = int(v) if numeric else v
        for p in evaluable:
            if (sid, p) not in published:
                issues.append(f"{sub['name']} {p}: calificaciones no publicadas")
        for c in comps:
            vals = row["periods"][c]
            row["finals"][c] = (_avg(vals.values()) if numeric else vals.get("P4")) if len(vals) == len(periods) else None
        row["final"] = _avg(row["finals"].values()) if numeric and all(row["finals"].values()) else None
        row["recovery"] = "Requiere" if numeric and row["final"] is not None and row["final"] < tpl["pass_mark"] else ""
        grid.append(row)
    notes = {n["period"]: n for n in await db.period_notes.find({"student_id": student_id, "academic_year_id": year_id}).to_list(10)}
    attendance, tp, ta = [], 0, 0
    for p in periods:
        n = notes.get(p, {})
        pr, ab = n.get("present"), n.get("absent")
        if pr is not None and ab is not None:
            tp, ta = tp + pr, ta + ab
        attendance.append({"period": p, "present": pr, "absent": ab, "pct": f"{round(100 * pr / (pr + ab))}%" if pr is not None and ab is not None and pr + ab else None})
        if p in evaluable and (pr is None or not n.get("observation")):
            issues.append(f"{p}: falta asistencia u observación del titular")
    titular = await db.teacher_assignments.find_one({"section_id": st["section_id"], "role": "titular", "status": "activa"})
    if not titular:
        issues.append("La sección no tiene maestro titular asignado")
    if not inst.get("director_name"):
        issues.append("La institución no tiene director/a registrado")
    order = [r["student_id"] for r in await roster(st["section_id"])]
    content = {"grid": grid, "attendance": attendance, "obs": {p: notes.get(p, {}).get("observation") for p in periods}}
    chash = hashlib.sha256(json.dumps(content, sort_keys=True, default=str).encode()).hexdigest()[:12]
    approvals = {}
    for a in await db.report_card_approvals.find({"student_id": student_id, "academic_year_id": year_id, "content_hash": chash}).to_list(10):
        approvals[a["stage"]] = {"by_name": a["by_name"], "at": a["at"]}
    status = "emitido" if "direccion" in approvals else "aprobado_docente" if "docente" in approvals else "borrador"
    year = await db.academic_years.find_one({"_id": ObjectId(year_id)})
    return {
        "student_id": student_id, "academic_year_id": year_id, "section_id": st["section_id"], "template": tpl, "status": status, "content_hash": chash,
        "cover": {"first_name": st["first_name"], "last_name": st["last_name"], "student_code": st["code"],
                  "order_number": order.index(student_id) + 1 if student_id in order else None, "institution": inst["name"], "campus": sec["campus_name"],
                  "district": inst.get("district"), "regional": inst.get("regional"), "year": year["name"], "level": sec.get("level"), "grade": sec["grade_name"],
                  "section": sec["name"], "teacher": titular["teacher_name"] if titular else None, "director": inst.get("director_name")},
        "grid": grid, "attendance": attendance, "attendance_total": {"present": tp, "absent": ta, "pct": f"{round(100 * tp / (tp + ta))}%" if tp + ta else None},
        "observations": content["obs"], "support": {p: notes.get(p, {}).get("support") for p in periods},
        "approvals": approvals, "inconsistencies": issues, "titular_teacher_id": titular["teacher_id"] if titular else None,
    }


@router.get("/report-cards/student/{student_id}")
async def card(student_id: str, ctx: Ctx = Depends(require("report_cards:view"))):
    data = await compile_card(ctx, student_id)
    if ctx.student_ids is not None and data["status"] != "emitido":
        raise HTTPException(403, "El boletín aún no ha sido emitido por la dirección")
    return data


@router.post("/report-cards/student/{student_id}/approve")
async def approve(student_id: str, body: ApproveIn, request: Request, ctx: Ctx = Depends(require("report_cards:view"))):
    data = await compile_card(ctx, student_id)
    if body.stage == "docente":
        if "report_cards:approve_teacher" not in ctx.perms or (ctx.user["role"] == "docente" and ctx.teacher_id != data["titular_teacher_id"]):
            raise HTTPException(403, "Solo el maestro titular de la sección aprueba como docente")
    else:
        if "report_cards:approve_director" not in ctx.perms:
            raise HTTPException(403, "Requiere validación de dirección")
        if "docente" not in data["approvals"]:
            raise HTTPException(409, "Falta la aprobación del docente titular para esta versión")
    if data["inconsistencies"]:
        raise HTTPException(422, "Corrija las inconsistencias antes de aprobar: " + "; ".join(data["inconsistencies"][:5]))
    if body.stage in data["approvals"]:
        raise HTTPException(409, "Esta versión ya fue aprobada en esta etapa")
    await db.report_card_approvals.insert_one({"institution_id": ctx.institution_id or ctx.user.get("institution_id"), "student_id": student_id,
                                               "academic_year_id": data["academic_year_id"], "content_hash": data["content_hash"], "stage": body.stage,
                                               "by": ctx.uid, "by_name": ctx.user["name"], "at": now_iso()})
    await audit(ctx, f"approve_{body.stage}", "report_cards", student_id, {"version": data["content_hash"]}, ip=request.client.host)
    return await compile_card(ctx, student_id)


def _rows(card: dict):
    comps, periods = [c["key"] for c in card["template"]["competencies"]], [p["key"] for p in card["template"]["periods"]]
    cols = [("subject", "Área curricular")] + [(f"{c}_{p}", f"{c} {p}") for c in comps for p in periods] + \
           [(f"F_{c}", f"Final {c}") for c in comps] + [("final", "Final área"), ("recovery", "Recuperación")]
    rows = []
    for r in card["grid"]:
        d = {"subject": r["subject"], "final": r["final"], "recovery": r["recovery"]}
        for c in comps:
            d.update({f"{c}_{p}": r["periods"][c].get(p) for p in periods})
            d[f"F_{c}"] = r["finals"].get(c)
        rows.append(d)
    return cols, rows


@router.get("/report-cards/student/{student_id}/export")
async def export_card(student_id: str, request: Request, format: str = "pdf", ctx: Ctx = Depends(require("report_cards:export"))):
    data = await compile_card(ctx, student_id)
    if ctx.student_ids is not None and data["status"] != "emitido":
        raise HTTPException(403, "El boletín aún no ha sido emitido por la dirección")
    await audit(ctx, "export", "report_cards", student_id, {"format": format, "status": data["status"]}, ip=request.client.host)
    name = f"boletin-{data['cover']['student_code']}"
    if format == "pdf":
        return Response(build_report_cards_pdf([data]), media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{name}.pdf"'})
    cols, rows = _rows(data)
    cv = data["cover"]
    meta = [("Estudiante", f"{cv['first_name']} {cv['last_name']} ({cv['student_code']})"), ("Grado", f"{cv['grade']} {cv['section']}"),
            ("Año escolar", cv["year"]), ("Docente titular", cv["teacher"]), ("Estado", data["status"]), ("Plantilla", data["template"]["official_validation"])]
    return export_response(format, name, "Informe de Aprendizaje", cols, rows, meta)


@router.get("/report-cards/section/{section_id}/pdf")
async def section_pdf(section_id: str, request: Request, only_issued: bool = False, ctx: Ctx = Depends(require("report_cards:export"))):
    if ctx.student_ids is not None:
        raise HTTPException(403, "Exportación masiva no permitida")
    await section_ctx(ctx, section_id)
    cards = [await compile_card(ctx, r["student_id"]) for r in await roster(section_id)]
    cards = [c for c in cards if not only_issued or c["status"] == "emitido"]
    if not cards:
        raise HTTPException(404, "Sin boletines para exportar")
    await audit(ctx, "export_bulk", "report_cards", section_id, {"count": len(cards)}, ip=request.client.host)
    return Response(build_report_cards_pdf(cards), media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="boletines-{section_id}.pdf"'})


@router.get("/minerd/coverage")
async def coverage(request: Request, format: Optional[str] = None, ctx: Ctx = Depends(require("teachers:view"))):
    year = await db.academic_years.find_one({**ctx.scope(), "is_current": True})
    secs = await db.sections.find({**ctx.scope(), "academic_year_id": str(year["_id"]) if year else None}).sort("grade_order", 1).to_list(500)
    rows = []
    for s in secs:
        sid = str(s["_id"])
        assigns = await db.teacher_assignments.find({"section_id": sid, "status": "activa"}).to_list(50)
        nsub = await db.subjects.count_documents({"institution_id": s["institution_id"], "status": "activo", "levels": {"$regex": s.get("level") or "-"}})
        tit = next((a for a in assigns if a["role"] == "titular"), None)
        rows.append({"section_id": sid, "section": f"{s['grade_name']} {s['name']}", "campus": s["campus_name"], "titular": tit["teacher_name"] if tit else None,
                     "subject_teachers": len([a for a in assigns if a["role"] == "asignatura"]), "subjects": nsub,
                     "students": s.get("enrolled_count", 0), "capacity": s["capacity"], "status": "cubierta" if tit else "sin titular"})
    if format:
        cols = [("section", "Sección"), ("campus", "Sede"), ("titular", "Titular"), ("subject_teachers", "Docentes asignatura"), ("subjects", "Áreas"),
                ("students", "Inscritos"), ("capacity", "Capacidad"), ("status", "Cobertura")]
        await audit(ctx, "export", "teacher_coverage", None, {"format": format}, ip=request.client.host)
        return export_response(format, "cobertura-docente", "Cobertura docente", cols, rows)
    return rows
