"""Entity registry: drives generic CRUD, listing, filtering and report exports."""
from fastapi import HTTPException

from erp.core.db import db
from erp.modules import schemas as s
from erp.shared.utils import aging_bucket, today_iso


def _overlap(a, b) -> bool:
    if not (a.get("days") and b.get("days") and a.get("start_time") and b.get("start_time")):
        return False
    if not set(a["days"].split(",")) & set(b["days"].split(",")):
        return False
    return a["start_time"] < b["end_time"] and b["start_time"] < a["end_time"]


async def _validate_assignment(data, exclude_id):
    data["section_label"] = f"{data.get('grade_name')} {data.get('section_name')}"
    if data["role"] in ("asignatura", "sustituto") and not data.get("subject_id"):
        raise HTTPException(422, "Las asignaciones de asignatura o sustitución requieren asignatura")
    if data.get("start_time") and (not data.get("end_time") or data["end_time"] <= data["start_time"]):
        raise HTTPException(422, "La hora de fin debe ser posterior a la de inicio")
    if data["status"] != "activa":
        return
    q = {"status": "activa", "institution_id": data["institution_id"]}
    if exclude_id:
        q["_id"] = {"$ne": exclude_id}
    if data["role"] == "titular" and await db.teacher_assignments.find_one({**q, "section_id": data["section_id"], "role": "titular"}):
        raise HTTPException(409, "La sección ya tiene un maestro titular activo. Finalice la asignación anterior para reemplazarlo.")
    if data["role"] == "asignatura" and await db.teacher_assignments.find_one(
            {**q, "section_id": data["section_id"], "subject_id": data["subject_id"], "role": "asignatura"}):
        raise HTTPException(409, "La asignatura ya tiene un docente activo en esta sección")
    others = await db.teacher_assignments.find({**q, "$or": [{"teacher_id": data["teacher_id"]}, {"section_id": data["section_id"]}]}).to_list(500)
    for o in others:
        if _overlap(data, o):
            who = "el docente" if o["teacher_id"] == data["teacher_id"] else "el aula/sección"
            raise HTTPException(409, f"Conflicto de horario: {who} ya está ocupado ({o.get('section_label')} {o['start_time']}-{o['end_time']})")


def _full_name(d):
    d["full_name"] = f"{d['first_name']} {d['last_name']}".strip()


def _sections_post(rows):
    for r in rows:
        cap = r.get("capacity") or 1
        r["occupancy"] = round(100 * r.get("enrolled_count", 0) / cap, 1)
        r["available"] = cap - r.get("enrolled_count", 0)
    return rows


def _receivables_post(rows):
    ref = today_iso()
    for r in rows:
        r["days_overdue"], r["bucket"] = aging_bucket(r["due_date"], ref)
    return rows


def _receivables_custom(q, params):
    if params.get("aging") == "vencidas":
        q["due_date"] = {"$lt": today_iso()}
    if params.get("aging") == "corriente":
        q["due_date"] = {"$gte": today_iso()}


ENTITIES = {
    "institutions": dict(coll="institutions", perm="institutions", title="Instituciones", scoped=False, global_write=True,
                         schema=s.InstitutionIn, search=["name", "code", "tax_id"], unique=[["code"]], sort="name", filters=["status"],
                         block=[("campuses", "institution_id")],
                         cols=[("code", "Código"), ("name", "Nombre"), ("tax_id", "RNC"), ("currency", "Moneda"), ("phone", "Teléfono"), ("email", "Correo"), ("status", "Estado")]),
    "campuses": dict(coll="campuses", perm="institutions", title="Campus / Sedes", schema=s.CampusIn, search=["name", "code"], unique=[["code"]],
                     sort="name", filters=["status"], block=[("sections", "campus_id"), ("students", "campus_id")],
                     cols=[("code", "Código"), ("name", "Nombre"), ("address", "Dirección"), ("phone", "Teléfono"), ("status", "Estado")]),
    "academic-years": dict(coll="academic_years", perm="academics", title="Años académicos", schema=s.AcademicYearIn, search=["name"],
                           unique=[["name"]], sort="-start_date", filters=["status"], block=[("terms", "academic_year_id"), ("sections", "academic_year_id")],
                           cols=[("name", "Año"), ("start_date", "Inicio"), ("end_date", "Fin"), ("is_current", "Actual"), ("status", "Estado")]),
    "terms": dict(coll="terms", perm="academics", title="Períodos académicos", schema=s.TermIn, search=["name", "year_name"],
                  refs={"academic_year_id": ("academic_years", "name", "year_name")}, sort="start_date", filters=["academic_year_id", "status"],
                  cols=[("year_name", "Año"), ("name", "Período"), ("start_date", "Inicio"), ("end_date", "Fin"), ("status", "Estado")]),
    "grades": dict(coll="grades", perm="academics", title="Grados", schema=s.GradeIn, search=["name"], unique=[["name"]], sort="order",
                   filters=["level"], block=[("sections", "grade_id")],
                   cols=[("order", "Orden"), ("name", "Grado"), ("level", "Nivel")]),
    "sections": dict(coll="sections", perm="academics", title="Secciones y cupos", schema=s.SectionIn, search=["name", "grade_name", "campus_name"],
                     unique=[["academic_year_id", "campus_id", "grade_id", "name"]], sort="grade_order", defaults={"enrolled_count": 0},
                     refs={"grade_id": ("grades", "name", "grade_name"), "campus_id": ("campuses", "name", "campus_name"),
                           "academic_year_id": ("academic_years", "name", "year_name")},
                     extra_refs=[("grade_id", "grades", "order", "grade_order"), ("grade_id", "grades", "level", "level")], section_field="_id",
                     filters=["academic_year_id", "campus_id", "grade_id", "shift"], block=[("enrollments", "section_id")], post=_sections_post,
                     cols=[("year_name", "Año"), ("campus_name", "Sede"), ("grade_name", "Grado"), ("name", "Sección"), ("shift", "Tanda"),
                           ("capacity", "Capacidad"), ("enrolled_count", "Inscritos"), ("available", "Disponibles"), ("occupancy", "Ocupación %")]),
    "fees": dict(coll="fees", perm="fees", title="Catálogo de tarifas", schema=s.FeeIn, search=["code", "name"], unique=[["code"]], sort="code",
                 filters=["category", "status"], sum=["amount"],
                 cols=[("code", "Código"), ("name", "Concepto"), ("category", "Categoría"), ("amount", "Monto"), ("recurring", "Recurrente"), ("status", "Estado")]),
    "guardians": dict(coll="guardians", perm="guardians", title="Padres y tutores", schema=s.GuardianIn, computed=_full_name,
                      search=["full_name", "document_id", "email", "phone"], unique=[["document_id"]], sort="last_name", filters=["relationship"],
                      cols=[("full_name", "Nombre"), ("document_id", "Cédula"), ("relationship", "Parentesco"), ("phone", "Teléfono"), ("email", "Correo")]),
    "students": dict(coll="students", perm="students", title="Estudiantes", schema=s.StudentIn, computed=_full_name, seq="student",
                     search=["code", "full_name", "document_id"], unique=[["document_id"]], sort="last_name", personal="_id", section_field="section_id",
                     refs={"campus_id": ("campuses", "name", "campus_name")}, filters=["status", "campus_id", "grade_name", "section_id", "gender"],
                     block=[("enrollments", "student_id"), ("invoices", "student_id")],
                     cols=[("code", "Matrícula"), ("full_name", "Nombre"), ("document_id", "Documento"), ("gender", "Sexo"), ("birth_date", "Nacimiento"),
                           ("campus_name", "Sede"), ("grade_name", "Grado"), ("section_name", "Sección"), ("status", "Estado")]),
    "subjects": dict(coll="subjects", perm="academics", title="Áreas curriculares / asignaturas", schema=s.SubjectIn, search=["code", "name"],
                      unique=[["code"]], sort="order", filters=["status"], block=[("teacher_assignments", "subject_id"), ("competency_grades", "subject_id")],
                      cols=[("order", "Orden"), ("code", "Código"), ("name", "Área curricular"), ("levels", "Niveles"), ("status", "Estado")]),
    "teachers": dict(coll="teachers", perm="teachers", title="Docentes", schema=s.TeacherIn, computed=_full_name, search=["full_name", "document_id", "specialty"],
                      unique=[["document_id"], ["user_id"]], sort="last_name", filters=["employment_status"], block=[("teacher_assignments", "teacher_id")],
                      cols=[("full_name", "Nombre"), ("document_id", "Cédula"), ("specialty", "Especialidad"), ("levels", "Niveles"), ("phone", "Teléfono"),
                            ("employment_status", "Estado laboral")]),
    "teacher-assignments": dict(coll="teacher_assignments", perm="teachers", title="Asignaciones docentes", schema=s.AssignmentIn,
                                 search=["teacher_name", "section_label", "subject_name"], sort="section_label", validate=_validate_assignment,
                                 filters=["teacher_id", "section_id", "role", "status", "academic_year_id"],
                                 refs={"teacher_id": ("teachers", "full_name", "teacher_name"), "section_id": ("sections", "name", "section_name"),
                                       "subject_id": ("subjects", "name", "subject_name")},
                                 extra_refs=[("section_id", "sections", "grade_name", "grade_name"), ("section_id", "sections", "academic_year_id", "academic_year_id"),
                                             ("section_id", "sections", "campus_name", "campus_name")],
                                 cols=[("teacher_name", "Docente"), ("section_label", "Sección"), ("campus_name", "Sede"), ("role", "Función"),
                                       ("subject_name", "Asignatura"), ("days", "Días"), ("start_time", "Desde"), ("end_time", "Hasta"),
                                       ("start_date", "Vigencia desde"), ("end_date", "Vigencia hasta"), ("status", "Estado")]),
    "grade-revisions": dict(coll="grade_revisions", perm="gradebook", title="Solicitudes de corrección de notas", readonly=True, sort="-created_at",
                             search=["student_name", "subject_name"], filters=["status", "section_id"], section_field="section_id",
                             cols=[("created_at", "Fecha"), ("student_name", "Estudiante"), ("subject_name", "Asignatura"), ("period", "Período"),
                                   ("old_scores", "Antes"), ("new_scores", "Propuesto"), ("reason", "Motivo"), ("requested_by_email", "Solicitante"), ("status", "Estado")]),
    "enrollments": dict(coll="enrollments", perm="enrollments", title="Matrículas", readonly=True, search=["student_name", "student_code"],
                        sort="-enrolled_at", personal="student_id", date_field="enrolled_at", section_field="section_id",
                        filters=["status", "academic_year_id", "section_id", "student_id", "type", "grade_name", "campus_id"],
                        cols=[("year_name", "Año"), ("student_code", "Matrícula"), ("student_name", "Estudiante"), ("grade_name", "Grado"),
                              ("section_name", "Sección"), ("campus_name", "Sede"), ("type", "Tipo"), ("status", "Estado"), ("enrolled_at", "Fecha")]),
    "invoices": dict(coll="invoices", perm="invoices", title="Facturas", readonly=True, search=["number", "student_name", "student_code"],
                     sort="-issue_date", personal="student_id", date_field="issue_date", filters=["status", "student_id"], sum=["total", "paid", "balance"],
                     cols=[("number", "Número"), ("student_code", "Matrícula"), ("student_name", "Estudiante"), ("issue_date", "Emisión"),
                           ("due_date", "Vencimiento"), ("total", "Total"), ("paid", "Pagado"), ("balance", "Saldo"), ("status", "Estado")]),
    "payments": dict(coll="payments", perm="payments", title="Pagos y recibos", readonly=True, search=["receipt_number", "student_name", "invoice_number", "reference"],
                     sort="-paid_at", personal="student_id", date_field="paid_at", filters=["method", "status", "student_id", "session_id", "invoice_id"],
                     sum=["amount"],
                     cols=[("receipt_number", "Recibo"), ("paid_at", "Fecha"), ("student_name", "Estudiante"), ("invoice_number", "Factura"),
                           ("method", "Método"), ("reference", "Referencia"), ("amount", "Monto"), ("cashier_name", "Cajero"), ("status", "Estado")]),
    "cash-sessions": dict(coll="cash_sessions", perm="cash", title="Sesiones de caja", readonly=True, search=["register_name", "cashier_name"],
                          sort="-opened_at", date_field="opened_at", filters=["status", "cashier_id"], sum=["difference"],
                          cols=[("register_name", "Caja"), ("cashier_name", "Cajero"), ("opened_at", "Apertura"), ("opening_amount", "Fondo inicial"),
                                ("closed_at", "Cierre"), ("expected_amount", "Esperado"), ("counted_amount", "Contado"), ("difference", "Diferencia"), ("status", "Estado")]),
    "receivables": dict(coll="invoices", perm="receivables", title="Cuentas por cobrar (antigüedad)", readonly=True,
                        base={"balance": {"$gt": 0.004}, "status": {"$ne": "anulada"}}, search=["number", "student_name", "student_code"],
                        sort="due_date", personal="student_id", filters=["student_id"], custom=_receivables_custom, post=_receivables_post,
                        sum=["balance"],
                        cols=[("number", "Factura"), ("student_code", "Matrícula"), ("student_name", "Estudiante"), ("due_date", "Vencimiento"),
                              ("total", "Total"), ("paid", "Pagado"), ("balance", "Saldo"), ("days_overdue", "Días vencidos"), ("bucket", "Antigüedad")]),
    "audit-logs": dict(coll="audit_logs", perm="audit", title="Bitácora de auditoría", readonly=True, search=["user_email", "action", "entity"],
                       sort="-at", date_field="at", filters=["action", "entity", "user_email"],
                       cols=[("at", "Fecha"), ("user_email", "Usuario"), ("action", "Acción"), ("entity", "Entidad"), ("entity_id", "ID"), ("ip", "IP")]),
    "users": dict(coll="users", perm="users", title="Usuarios", readonly=True, search=["name", "email"], sort="name", filters=["role"],
                  cols=[("name", "Nombre"), ("email", "Correo"), ("role", "Rol"), ("is_active", "Activo"), ("last_login", "Último acceso")]),
}
