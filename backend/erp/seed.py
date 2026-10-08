"""Seed: admin (from .env) + reproducible demo dataset. CLI: python -m erp.seed [--reset]"""
import asyncio
import logging
import random
import sys
from datetime import date, datetime, timedelta, timezone

from pymongo import ASCENDING, DESCENDING

from erp.core import config
from erp.core.db import db
from erp.core.security import hash_password, verify_password
from erp.shared.utils import money, invoice_status
from erp.seed_academic import ensure_templates, seed_academic_staff

log = logging.getLogger("seed")
COLLECTIONS = ["institutions", "campuses", "academic_years", "terms", "grades", "sections", "fees", "guardians", "students",
               "enrollments", "invoices", "payments", "cash_sessions", "audit_logs", "counters", "sessions", "login_attempts",
               "subjects", "teachers", "teacher_assignments", "competency_grades", "grade_periods", "period_notes", "grade_revisions",
               "report_card_approvals"]


async def ensure_indexes():
    await db.users.create_index("email", unique=True)
    await db.login_attempts.create_index("identifier")
    await db.sessions.create_index("jti", unique=True)
    await db.sessions.create_index("expires_at", expireAfterSeconds=0)
    await db.students.create_index([("institution_id", ASCENDING), ("code", ASCENDING)], unique=True)
    await db.students.create_index([("institution_id", ASCENDING), ("status", ASCENDING), ("last_name", ASCENDING)])
    await db.guardians.create_index("student_ids")
    await db.sections.create_index([("institution_id", ASCENDING), ("academic_year_id", ASCENDING), ("grade_order", ASCENDING)])
    await db.enrollments.create_index([("student_id", ASCENDING), ("academic_year_id", ASCENDING)], unique=True,
                                      partialFilterExpression={"status": "activa"}, name="uq_active_enrollment")
    await db.invoices.create_index([("institution_id", ASCENDING), ("number", ASCENDING)], unique=True)
    await db.invoices.create_index([("institution_id", ASCENDING), ("status", ASCENDING), ("due_date", ASCENDING)])
    await db.invoices.create_index("student_id")
    await db.payments.create_index("idempotency_key", unique=True)
    await db.payments.create_index([("institution_id", ASCENDING), ("paid_at", DESCENDING)])
    await db.payments.create_index("session_id")
    await db.cash_sessions.create_index("cashier_id", unique=True, partialFilterExpression={"status": "abierta"}, name="uq_open_cash")
    await db.audit_logs.create_index([("institution_id", ASCENDING), ("at", DESCENDING)])
    await db.competency_grades.create_index([("student_id", ASCENDING), ("section_id", ASCENDING), ("subject_id", ASCENDING), ("period", ASCENDING)], unique=True)
    await db.grade_periods.create_index([("section_id", ASCENDING), ("subject_id", ASCENDING), ("period", ASCENDING)], unique=True)
    await db.period_notes.create_index([("student_id", ASCENDING), ("section_id", ASCENDING), ("period", ASCENDING)], unique=True)
    await db.teacher_assignments.create_index([("section_id", ASCENDING), ("role", ASCENDING), ("status", ASCENDING)])
    await db.report_card_approvals.create_index([("student_id", ASCENDING), ("academic_year_id", ASCENDING), ("content_hash", ASCENDING),
                                                 ("stage", ASCENDING)], unique=True)
    await ensure_templates()


async def seed_admin():
    existing = await db.users.find_one({"email": config.ADMIN_EMAIL})
    if existing is None:
        await db.users.insert_one({"email": config.ADMIN_EMAIL, "password_hash": hash_password(config.ADMIN_PASSWORD), "name": "Administrador General",
                                   "role": "superadmin", "institution_id": None, "is_active": True, "created_at": datetime.now(timezone.utc).isoformat()})
        log.info("Superadmin creado: %s", config.ADMIN_EMAIL)
    elif not verify_password(config.ADMIN_PASSWORD, existing["password_hash"]):
        await db.users.update_one({"_id": existing["_id"]}, {"$set": {"password_hash": hash_password(config.ADMIN_PASSWORD), "is_active": True}})


FIRST_M = ["Juan", "Carlos", "Luis", "José", "Miguel", "Andrés", "Rafael", "Daniel", "Gabriel", "Samuel", "Mateo", "Diego", "Javier", "Adrián", "Tomás", "Emilio"]
FIRST_F = ["María", "Ana", "Laura", "Sofía", "Valentina", "Camila", "Isabella", "Lucía", "Paula", "Gabriela", "Elena", "Daniela", "Mariana", "Carolina", "Alejandra", "Natalia"]
LAST = ["Pérez", "Rodríguez", "Martínez", "García", "Fernández", "López", "Gómez", "Díaz", "Reyes", "Castillo", "Jiménez", "Peña", "Santana", "Rosario", "Vásquez",
        "Mejía", "Cruz", "Núñez", "Ramírez", "Batista", "Herrera", "Medina", "Guzmán", "Polanco", "Tavárez", "Almonte", "Cabrera", "Sánchez"]
GRADES = [("Pre-primario", "inicial")] + [(f"{n} de Primaria", "primaria") for n in ("1ro", "2do", "3ro", "4to", "5to", "6to")] + \
         [(f"{n} de Secundaria", "secundaria") for n in ("1ro", "2do", "3ro", "4to", "5to", "6to")]


class Builder:
    def __init__(self, rnd: random.Random, today: date):
        self.r, self.today = rnd, today
        self.inv_seq, self.rec_seq, self.stu_seq = {}, {}, {}
        self.invoices, self.payments, self.sessions = [], [], {}

    def iso(self, d: date, hour=9) -> str:
        return datetime(d.year, d.month, d.day, hour, self.r.randint(0, 59), tzinfo=timezone.utc).isoformat()

    def num(self, store, inst, code, kind):
        store[inst] = store.get(inst, 0) + 1
        return f"{code}-{kind}-{store[inst]:06d}"

    def invoice(self, inst, code, st, fee, issue: date, due: date, period=None):
        total = fee["amount"]
        inv = {"_id": None, "institution_id": inst, "number": self.num(self.inv_seq, inst, code, "F"), "student_id": st["sid"],
               "student_name": st["full_name"], "student_code": st["code"], "grade_name": st.get("grade_name"),
               "issue_date": issue.isoformat(), "due_date": due.isoformat(),
               "lines": [{"fee_id": fee["id"], "description": f"{fee['name']}{' ' + period if period else ''}", "category": fee["category"],
                          "quantity": 1, "unit_price": total, "discount": 0.0, "total": total}],
               "subtotal": total, "discount_total": 0.0, "total": total, "paid": 0.0, "balance": total, "status": "pendiente",
               "batch_key": f"{fee['id']}:{period}" if period else None, "created_at": self.iso(issue, 7)}
        self.invoices.append(inv)
        return inv

    def pay(self, inst, code, inv, amount, when: date, cashier):
        if when > self.today:
            return
        amount = money(min(amount, inv["balance"]))
        if amount <= 0:
            return
        key = (inst, when.isoformat())
        if key not in self.sessions:
            self.sessions[key] = {"institution_id": inst, "cashier_id": cashier["id"], "cashier_name": cashier["name"], "register_name": "Caja Principal",
                                  "opening_amount": 5000.0, "opened_at": self.iso(when, 7), "closed_at": self.iso(when, 17), "status": "cerrada", "_pays": []}
        method = self.r.choices(["efectivo", "transferencia", "tarjeta", "deposito", "cheque"], [40, 30, 20, 7, 3])[0]
        p = {"institution_id": inst, "invoice_number": inv["number"], "_inv": inv, "student_id": inv["student_id"], "student_name": inv["student_name"],
             "student_code": inv["student_code"], "amount": amount, "method": method, "reference": None if method == "efectivo" else f"REF{self.r.randint(100000, 999999)}",
             "cashier_id": cashier["id"], "cashier_name": cashier["name"], "status": "aplicado", "paid_at": self.iso(when, self.r.randint(8, 16)), "_skey": key}
        self.payments.append(p)
        inv["paid"] = money(inv["paid"] + amount)
        inv["balance"] = money(inv["total"] - inv["paid"])
        inv["status"] = invoice_status(inv["paid"], inv["balance"])


async def _insert_many(coll, docs):
    if docs:
        res = await db[coll].insert_many(docs)
        return [str(i) for i in res.inserted_ids]
    return []


async def _seed_institution(b: Builder, spec: dict, cashier_name: str):
    r = b.r
    inst_id = str((await db.institutions.insert_one({k: spec[k] for k in ("name", "code", "tax_id", "currency", "timezone", "address", "phone", "email",
                                                                          "director_name", "district", "regional")}
                                                    | {"status": "activo", "created_at": b.iso(date(2024, 1, 15))})).inserted_id)
    code = spec["code"]
    campus_ids = await _insert_many("campuses", [{"institution_id": inst_id, "name": n, "code": c, "address": a, "status": "activo"} for n, c, a in spec["campuses"]])
    campuses = list(zip(campus_ids, [c[0] for c in spec["campuses"]]))
    years = [("2025-2026", date(2025, 8, 18), date(2026, 6, 26), False, "cerrado"), ("2026-2027", date(2026, 8, 17), date(2027, 6, 25), True, "activo")]
    year_ids = await _insert_many("academic_years", [{"institution_id": inst_id, "name": n, "start_date": s.isoformat(), "end_date": e.isoformat(),
                                                      "is_current": cur, "status": st} for n, s, e, cur, st in years])
    terms = []
    for yid, (yn, s, e, _, st) in zip(year_ids, years):
        span = (e - s).days // 4
        for i in range(4):
            ts = s + timedelta(days=span * i)
            terms.append({"institution_id": inst_id, "academic_year_id": yid, "year_name": yn, "name": f"Período {i + 1}", "start_date": ts.isoformat(),
                          "end_date": (ts + timedelta(days=span - 1)).isoformat(), "status": "cerrado" if ts + timedelta(days=span) < b.today else "abierto"})
    await _insert_many("terms", terms)
    grades = GRADES[: spec["grade_count"]]
    grade_ids = await _insert_many("grades", [{"institution_id": inst_id, "name": g, "level": lv, "order": i} for i, (g, lv) in enumerate(grades)])
    sections = []
    for yid, (yn, *_rest) in zip(year_ids, years):
        for gi, (gid, (gname, lv)) in enumerate(zip(grade_ids, grades)):
            for ci, (cid, cname) in enumerate(campuses):
                sections.append({"institution_id": inst_id, "academic_year_id": yid, "year_name": yn, "campus_id": cid, "campus_name": cname,
                                 "grade_id": gid, "grade_name": gname, "grade_order": gi, "level": lv, "name": "AB"[ci % 2] if len(campuses) > 1 else "A",
                                 "capacity": spec["capacity"], "shift": "matutino" if ci == 0 else "vespertino", "enrolled_count": 0})
    sec_ids = await _insert_many("sections", sections)
    for s, sid in zip(sections, sec_ids):
        s["id"] = sid
    fees = [{"institution_id": inst_id, "code": c, "name": n, "category": cat, "amount": float(a), "recurring": rec, "status": "activo"}
            for c, n, cat, a, rec in spec["fees"]]
    for f, fid in zip(fees, await _insert_many("fees", fees)):
        f["id"] = fid
    fee = {f["code"]: f for f in fees}

    students, guardians = [], []
    for i in range(spec["students"]):
        gender = r.choice("MF")
        ln1, ln2 = r.choice(LAST), r.choice(LAST)
        if i % 6 == 5 and guardians:
            g = guardians[-1]
            ln1 = g["last_name"].split()[0]
        else:
            gf = r.choice(["madre", "padre"])
            g = {"institution_id": inst_id, "first_name": r.choice(FIRST_F if gf == "madre" else FIRST_M), "last_name": f"{ln1} {r.choice(LAST)}",
                 "document_id": f"{r.randint(1, 402):03d}-{r.randint(1000000, 9999999)}-{r.randint(0, 9)}", "relationship": gf,
                 "phone": f"809-{r.randint(200, 999)}-{r.randint(1000, 9999)}", "email": None, "address": spec["address"], "student_ids": []}
            g["full_name"] = f"{g['first_name']} {g['last_name']}"
            g["email"] = f"{g['first_name'].lower()}.{i}@correo-demo.do".replace("í", "i").replace("é", "e").replace("á", "a").replace("ó", "o").replace("ú", "u")
            guardians.append(g)
        gi = r.randrange(len(grades))
        age = 5 + gi
        b.stu_seq[inst_id] = b.stu_seq.get(inst_id, 0) + 1
        status = "activo"
        if i % 37 == 0:
            status = "prospecto"
        elif i % 41 == 0:
            status = "retirado"
        st = {"institution_id": inst_id, "code": f"{code}-{b.stu_seq[inst_id]:05d}", "first_name": r.choice(FIRST_M if gender == "M" else FIRST_F),
              "last_name": f"{ln1} {ln2}", "gender": gender, "birth_date": date(b.today.year - age, r.randint(1, 12), r.randint(1, 28)).isoformat(),
              "document_id": None, "campus_id": campuses[i % len(campuses)][0], "campus_name": campuses[i % len(campuses)][1], "status": status,
              "email": None, "phone": None, "address": spec["address"], "_g": g, "_gi": gi,
              "_profile": r.choices(["puntual", "tardio", "moroso"], [72, 18, 10])[0], "created_at": b.iso(date(2025, 6, 1))}
        st["full_name"] = f"{st['first_name']} {st['last_name']}"
        students.append(st)
    g_ids = await _insert_many("guardians", guardians)
    for g, gid in zip(guardians, g_ids):
        g["id"] = gid

    sec_index = {(s["academic_year_id"], s["grade_order"], s["campus_id"]): s for s in sections}
    enrollments = []
    for st in students:
        st["guardian_ids"] = [st["_g"]["id"]]
    s_ids = await _insert_many("students", [{k: v for k, v in st.items() if not k.startswith("_")} for st in students])
    cashier = {"id": "seed", "name": cashier_name}
    for st, sid in zip(students, s_ids):
        st["sid"] = sid
        st["_g"]["student_ids"].append(sid)
        if st["status"] == "prospecto":
            continue
        for yi, yid in enumerate(year_ids):
            gi = st["_gi"] - (1 - yi)
            if gi < 0:
                continue
            sec = sec_index[(yid, gi, st["campus_id"])]
            if sec["enrolled_count"] >= sec["capacity"]:
                continue
            current = yi == 1
            status = "activa" if current else "finalizada"
            if current and st["status"] == "retirado":
                status = "retirada"
            if status != "retirada":
                sec["enrolled_count"] += 1 if current else 0
            enrollments.append({"institution_id": inst_id, "student_id": sid, "student_name": st["full_name"], "student_code": st["code"],
                                "section_id": sec["id"], "section_name": sec["name"], "grade_name": sec["grade_name"], "grade_id": sec["grade_id"],
                                "campus_id": sec["campus_id"], "campus_name": sec["campus_name"], "academic_year_id": yid, "year_name": years[yi][0],
                                "type": "reinscripcion" if (yi == 1 and gi > 0 and st["_gi"] > 0 and r.random() > 0.2) else "nueva", "status": status,
                                "enrolled_at": b.iso(years[yi][1] - timedelta(days=r.randint(10, 60)))})
            if current:
                st.update({"section_id": sec["id"], "section_name": sec["name"], "grade_name": sec["grade_name"], "grade_id": sec["grade_id"],
                           "academic_year_id": yid, "year_name": years[1][0]})
            _bill_year(b, inst_id, code, st, fee, years[yi], current, status, cashier)
    e_ids = await _insert_many("enrollments", enrollments)
    for e, eid in zip(enrollments, e_ids):
        if e["status"] == "activa":
            await db.students.update_one({"_id": __import__("bson").ObjectId(e["student_id"])},
                                         {"$set": {k: e[k] for k in ("section_id", "section_name", "grade_name", "grade_id", "academic_year_id", "year_name")}
                                          | {"enrollment_id": eid}})
    for s in sections:
        await db.sections.update_one({"_id": __import__("bson").ObjectId(s["id"])}, {"$set": {"enrolled_count": s["enrolled_count"]}})
    for g in guardians:
        await db.guardians.update_one({"_id": __import__("bson").ObjectId(g["id"])}, {"$set": {"student_ids": g["student_ids"]}})
    return inst_id, guardians, students


def _bill_year(b: Builder, inst, code, st, fee, year, current, status, cashier):
    r, prof = b.r, st["_profile"]
    start = year[1]
    mat = b.invoice(inst, code, st, fee["MAT-01"], start - timedelta(days=45), start - timedelta(days=15))
    b.pay(inst, code, mat, mat["total"], start - timedelta(days=r.randint(15, 40)), cashier)
    months = [(start.replace(day=1) + timedelta(days=32 * i)).replace(day=1) for i in range(10)]
    uses_transport = hash(st["code"]) % 4 == 0
    for idx, m in enumerate(months):
        issue, due = m, m.replace(day=10)
        if issue > b.today or (status == "retirada" and idx > 0):
            break
        period = m.strftime("%Y-%m")
        items = [fee["MEN-01"]] + ([fee["TRA-01"]] if uses_transport and "TRA-01" in fee else [])
        for f in items:
            inv = b.invoice(inst, code, st, f, issue, due, period)
            if prof == "puntual":
                b.pay(inst, code, inv, inv["total"], due - timedelta(days=r.randint(0, 8)), cashier)
            elif prof == "tardio":
                if not current or r.random() > 0.35:
                    b.pay(inst, code, inv, inv["total"], due + timedelta(days=r.randint(5, 40)), cashier)
            else:
                if not current:
                    b.pay(inst, code, inv, inv["total"], due + timedelta(days=r.randint(10, 60)), cashier)
                elif idx == 0:
                    b.pay(inst, code, inv, inv["total"] * 0.5, due + timedelta(days=12), cashier)


async def _flush_finance(b: Builder):
    inv_docs = [{k: v for k, v in inv.items() if k != "_id"} for inv in b.invoices]
    ids = await _insert_many("invoices", inv_docs)
    for inv, iid in zip(b.invoices, ids):
        inv["_id"] = iid
    sess_docs = list(b.sessions.values())
    b.payments.sort(key=lambda p: p["paid_at"])
    for p in b.payments:
        b.sessions[p["_skey"]]["_pays"].append(p)
    for s in sess_docs:
        totals = {}
        for p in s["_pays"]:
            t = totals.setdefault(p["method"], {"total": 0.0, "count": 0})
            t["total"] = money(t["total"] + p["amount"])
            t["count"] += 1
        expected = money(s["opening_amount"] + totals.get("efectivo", {}).get("total", 0))
        diff = -150.0 if b.r.random() < 0.03 else 0.0
        s.update({"totals_by_method": totals, "expected_amount": expected, "counted_amount": money(expected + diff), "difference": diff})
    sess_ids = await _insert_many("cash_sessions", [{k: v for k, v in s.items() if k != "_pays"} for s in sess_docs])
    for s, sid in zip(sess_docs, sess_ids):
        for p in s["_pays"]:
            p["session_id"] = sid
    inst_codes = {}
    pays = []
    for i, p in enumerate(b.payments):
        code = p["_inv"]["number"].split("-F-")[0]
        p["receipt_number"] = b.num(b.rec_seq, p["institution_id"], code, "R")
        inst_codes[p["institution_id"]] = code
        p["invoice_id"] = p["_inv"]["_id"]
        p["idempotency_key"] = f"seed-{i:07d}"
        pays.append({k: v for k, v in p.items() if not k.startswith("_")})
    await _insert_many("payments", pays)
    for inst, n in b.inv_seq.items():
        await db.counters.update_one({"_id": f"invoice:{inst}"}, {"$set": {"seq": n}}, upsert=True)
    for inst, n in b.rec_seq.items():
        await db.counters.update_one({"_id": f"receipt:{inst}"}, {"$set": {"seq": n}}, upsert=True)
    for inst, n in b.stu_seq.items():
        await db.counters.update_one({"_id": f"student:{inst}"}, {"$set": {"seq": n}}, upsert=True)


INSTITUTIONS = [
    {"name": "Colegio Horizonte del Saber", "code": "CHS", "tax_id": "1-01-00000-1", "currency": "DOP", "timezone": "America/Santo_Domingo",
     "address": "Av. Principal #100, Santo Domingo", "phone": "809-555-0100", "email": "info@horizonte-demo.edu.do",
     "director_name": "Lic. Rafael Castillo", "district": "15-03 (demo)", "regional": "15 Santo Domingo (demo)",
     "campuses": [("Sede Central", "CEN", "Av. Principal #100"), ("Sede Norte", "NOR", "Calle Norte #25")], "grade_count": 13, "capacity": 30,
     "students": 420, "fees": [("MAT-01", "Matrícula anual", "matricula", 18500, False), ("MEN-01", "Mensualidad", "mensualidad", 9800, True),
                               ("TRA-01", "Transporte escolar", "transporte", 3500, True), ("CAF-01", "Plan de cafetería", "cafeteria", 2800, True),
                               ("SEG-01", "Seguro escolar", "servicio", 1500, False), ("REC-01", "Recargo por mora", "recargo", 500, False),
                               ("UNI-01", "Uniforme completo", "material", 4200, False)]},
    {"name": "Instituto Bilingüe Costa Azul", "code": "IBCA", "tax_id": "1-02-00000-2", "currency": "DOP", "timezone": "America/Santo_Domingo",
     "address": "Calle Marina #8, Puerto Plata", "phone": "809-555-0200", "email": "info@costaazul-demo.edu.do",
     "director_name": "Licda. Elena Cruz", "district": "11-01 (demo)", "regional": "11 Puerto Plata (demo)",
     "campuses": [("Campus Único", "UNI", "Calle Marina #8")], "grade_count": 7, "capacity": 12, "students": 50,
     "fees": [("MAT-01", "Inscripción", "matricula", 12000, False), ("MEN-01", "Colegiatura mensual", "mensualidad", 7500, True)]},
]


def _users(inst_id, inst2_id, guardian, student):
    pw = hash_password(config.DEMO_PASSWORD)
    base = [("admin.colegio@schoolerp.local", "Laura Martínez (Admin)", "admin_institucional", inst_id, {}),
            ("director@schoolerp.local", "Rafael Castillo (Director)", "director", inst_id, {}),
            ("secretaria@schoolerp.local", "Carmen Peña (Secretaría)", "secretaria", inst_id, {}),
            ("cajero@schoolerp.local", "Pedro Santana (Cajero)", "cajero", inst_id, {}),
            ("contador@schoolerp.local", "Ana Reyes (Contadora)", "contador", inst_id, {}),
            ("auditor@schoolerp.local", "Miguel Herrera (Auditor)", "auditor", inst_id, {}),
            ("docente@schoolerp.local", "Sofía Medina (Docente)", "docente", inst_id, {}),
            ("tutor@schoolerp.local", guardian["full_name"] + " (Tutor)", "tutor", inst_id, {"guardian_id": guardian["id"]}),
            ("estudiante@schoolerp.local", student["full_name"] + " (Estudiante)", "estudiante", inst_id, {"student_id": student["sid"]}),
            ("admin.costa@schoolerp.local", "Elena Cruz (Admin Costa Azul)", "admin_institucional", inst2_id, {})]
    now = datetime.now(timezone.utc).isoformat()
    return [{"email": e, "name": n, "role": ro, "institution_id": i, "password_hash": pw, "is_active": True, "created_at": now, **extra}
            for e, n, ro, i, extra in base]


async def seed_demo(force: bool = False):
    if not force and await db.institutions.count_documents({}) > 0:
        return
    today = date.today()
    b = Builder(random.Random(2026), today)
    inst_id, guardians, students = await _seed_institution(b, INSTITUTIONS[0], "Pedro Santana (Cajero)")
    inst2_id, _, _ = await _seed_institution(b, INSTITUTIONS[1], "Cajero Costa Azul")
    await _flush_finance(b)
    guardian = next(g for g in guardians if len(g["student_ids"]) > 1)
    student = next(s for s in students if s["status"] == "activo" and s["sid"] in guardian["student_ids"])
    users = _users(inst_id, inst2_id, guardian, student)
    await db.users.delete_many({"email": {"$in": [u["email"] for u in users]}})
    await db.users.insert_many(users)
    cashier = await db.users.find_one({"email": "cajero@schoolerp.local"})
    await db.payments.update_many({"cashier_id": "seed", "institution_id": inst_id}, {"$set": {"cashier_id": str(cashier["_id"])}})
    await db.cash_sessions.update_many({"cashier_id": "seed", "institution_id": inst_id}, {"$set": {"cashier_id": str(cashier["_id"])}})
    await db.audit_logs.insert_one({"institution_id": inst_id, "user_email": "sistema", "action": "seed", "entity": "platform",
                                    "details": {"invoices": len(b.invoices), "payments": len(b.payments)}, "at": datetime.now(timezone.utc).isoformat()})
    docente = await db.users.find_one({"email": "docente@schoolerp.local"})
    await seed_academic_staff(b.r, inst_id, str(docente["_id"]))
    await seed_academic_staff(b.r, inst2_id)
    log.info("Demo seed: %s facturas, %s pagos", len(b.invoices), len(b.payments))


async def _cli():
    if "--reset" in sys.argv:
        if config.APP_ENV == "production":
            raise SystemExit("Reinicio de seed bloqueado en producción")
        for c in COLLECTIONS:
            await db[c].delete_many({})
        await db.users.delete_many({"role": {"$ne": "superadmin"}})
    await ensure_indexes()
    await seed_admin()
    await seed_demo(force="--reset" in sys.argv)
    print(f"Seed listo. Superadmin: {config.ADMIN_EMAIL}")


if __name__ == "__main__":
    asyncio.run(_cli())
