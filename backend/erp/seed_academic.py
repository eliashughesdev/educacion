"""Seed MINERD: plantillas, áreas curriculares, docentes titulares y notas P1 de demostración."""
import random
from datetime import datetime, timezone

from erp.core.db import db
from erp.modules.minerd_templates import TEMPLATES, SUBJECTS

FIRST = ["Rosa", "Pedro", "Carmen", "Luis", "Altagracia", "Ramón", "Mercedes", "Francisco", "Yolanda", "Héctor", "Milagros", "Julio"]
LAST = ["Peña", "Reyes", "Castillo", "Mejía", "Rosario", "Batista", "Guzmán", "Polanco", "Tavárez", "Almonte", "Cabrera", "Núñez"]


async def ensure_templates():
    for t in TEMPLATES:
        await db.report_card_templates.update_one({"key": t["key"], "version": t["version"]}, {"$set": t}, upsert=True)


async def seed_academic_staff(r: random.Random, inst_id: str, docente_user_id=None):
    now = datetime.now(timezone.utc).isoformat()
    subs = [{"institution_id": inst_id, "code": c, "name": n, "levels": lv, "order": i, "status": "activo"} for i, (c, n, lv) in enumerate(SUBJECTS)]
    sub_ids = [str(i) for i in (await db.subjects.insert_many(subs)).inserted_ids]
    year = await db.academic_years.find_one({"institution_id": inst_id, "is_current": True})
    sections = await db.sections.find({"institution_id": inst_id, "academic_year_id": str(year["_id"])}).sort("grade_order", 1).to_list(100)
    target = next((s for s in sections if s["grade_order"] == 1 and s["name"] == "A"), None)
    for s in sections:
        t = {"institution_id": inst_id, "first_name": r.choice(FIRST), "last_name": f"{r.choice(LAST)} {r.choice(LAST)}",
             "document_id": f"{r.randint(1, 402):03d}-{r.randint(1000000, 9999999)}-{r.randint(0, 9)}", "specialty": f"Educación {s['level'].capitalize()}",
             "levels": s["level"], "employment_status": "activo", "hire_date": "2022-08-15", "phone": f"809-{r.randint(200, 999)}-{r.randint(1000, 9999)}",
             "email": None, "user_id": docente_user_id if (docente_user_id and s is target) else None, "created_at": now}
        t["full_name"] = f"{t['first_name']} {t['last_name']}"
        tid = str((await db.teachers.insert_one(t)).inserted_id)
        await db.teacher_assignments.insert_one({
            "institution_id": inst_id, "teacher_id": tid, "teacher_name": t["full_name"], "section_id": str(s["_id"]), "section_name": s["name"],
            "grade_name": s["grade_name"], "section_label": f"{s['grade_name']} {s['name']}", "campus_name": s["campus_name"],
            "academic_year_id": s["academic_year_id"], "subject_id": None, "subject_name": None, "role": "titular", "start_date": "2026-08-17",
            "end_date": None, "days": None, "start_time": None, "end_time": None, "status": "activa", "created_at": now})
    if not (docente_user_id and target):
        return
    sid = str(target["_id"])
    enr = await db.enrollments.find({"section_id": sid, "status": "activa"}).to_list(100)
    prim = [i for i, s in zip(sub_ids, subs) if "primaria" in s["levels"]]
    grades, notes = [], []
    for e in enr:
        base = r.randint(62, 96)
        for sub_id in prim:
            grades.append({"institution_id": inst_id, "academic_year_id": target["academic_year_id"], "section_id": sid, "subject_id": sub_id,
                           "student_id": e["student_id"], "period": "P1", "updated_at": now,
                           "scores": {c: float(max(50, min(100, base + r.randint(-6, 6)))) for c in ("C1", "C2", "C3")}})
        ab = r.randint(0, 6)
        notes.append({"institution_id": inst_id, "academic_year_id": target["academic_year_id"], "section_id": sid, "student_id": e["student_id"],
                      "period": "P1", "present": 38 - ab, "absent": ab, "updated_at": now, "support": "Lectura diaria en casa de 15 minutos.",
                      "observation": "Participa activamente; avanza en comprensión lectora." if base > 75 else "Requiere acompañamiento en lectoescritura y cálculo."})
    if grades:
        await db.competency_grades.insert_many(grades)
        await db.period_notes.insert_many(notes)
    await db.grade_periods.insert_many([{"institution_id": inst_id, "section_id": sid, "subject_id": x, "period": "P1",
                                         "status": "publicado" if x != prim[-1] else "borrador", "published_at": now} for x in prim])
