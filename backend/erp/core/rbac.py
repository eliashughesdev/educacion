CRUD = ["view", "create", "update", "delete", "export"]
MODULES = {
    "dashboard": ["view"],
    "institutions": CRUD,
    "academics": CRUD,
    "students": CRUD,
    "guardians": CRUD,
    "enrollments": ["view", "create", "update", "withdraw", "export"],
    "fees": CRUD,
    "invoices": ["view", "create", "void", "bulk", "export"],
    "cash": ["view", "open", "close", "export"],
    "payments": ["view", "create", "reverse", "export"],
    "receivables": ["view", "export"],
    "reports": ["view", "export"],
    "audit": ["view", "export"],
    "users": ["view", "create", "update", "export"],
    "teachers": CRUD,
    "gradebook": ["view", "edit", "publish", "approve_revision"],
    "report_cards": ["view", "approve_teacher", "approve_director", "export"],
}
ALL = [f"{m}:{a}" for m, acts in MODULES.items() for a in acts]
VIEWS = [p for p in ALL if p.endswith(":view")]
EXPORTS = [p for p in ALL if p.endswith(":export")]


def _mods(*mods, actions=None):
    return [f"{m}:{a}" for m in mods for a in MODULES[m] if actions is None or a in actions]


ROLES = {
    "superadmin": {"label": "Superadministrador de plataforma", "global": True, "perms": ALL},
    "admin_institucional": {"label": "Administrador institucional", "perms": [p for p in ALL if p != "institutions:delete"]},
    "director": {"label": "Director general", "perms": VIEWS + EXPORTS + ["report_cards:approve_director", "gradebook:approve_revision"]
                 + _mods("teachers")},
    "secretaria": {"label": "Secretaría académica", "perms": ["dashboard:view", "academics:view", "reports:view", "reports:export",
                   "invoices:view", "receivables:view", "teachers:view", "report_cards:view", "report_cards:export"]
                   + _mods("students", "guardians", "enrollments")},
    "cajero": {"label": "Cajero", "perms": ["dashboard:view", "students:view", "invoices:view", "invoices:create", "receivables:view",
               "cash:view", "cash:open", "cash:close", "cash:export", "payments:view", "payments:create", "payments:export",
               "reports:view", "fees:view"]},
    "contador": {"label": "Contador", "perms": ["dashboard:view", "students:view", "reports:view", "reports:export", "cash:view", "cash:export"]
                 + _mods("fees", "invoices", "receivables") + _mods("payments", actions=["view", "reverse", "export"])},
    "auditor": {"label": "Auditor interno", "perms": VIEWS + EXPORTS},
    "docente": {"label": "Docente", "perms": ["students:view", "academics:view", "enrollments:view", "gradebook:view", "gradebook:edit",
                "gradebook:publish", "report_cards:view", "report_cards:approve_teacher", "report_cards:export"]},
    "tutor": {"label": "Padre/Madre/Tutor legal", "personal": True, "perms": ["students:view", "invoices:view", "payments:view",
               "report_cards:view", "report_cards:export"]},
    "estudiante": {"label": "Estudiante", "personal": True, "perms": ["students:view", "invoices:view", "payments:view",
                    "report_cards:view", "report_cards:export"]},
}


def permissions_for(role: str) -> list:
    return ROLES.get(role, {}).get("perms", [])
