import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Optional

import bcrypt
import jwt
from bson import ObjectId
from fastapi import Depends, HTTPException, Request

from erp.core import config
from erp.core.db import db
from erp.core.rbac import ROLES, permissions_for

ALGO = "HS256"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def create_access_token(user_id: str, email: str) -> str:
    exp = datetime.now(timezone.utc) + timedelta(minutes=config.ACCESS_TOKEN_MINUTES)
    return jwt.encode({"sub": user_id, "email": email, "exp": exp, "type": "access"}, config.JWT_SECRET, algorithm=ALGO)


async def create_refresh_token(user_id: str) -> str:
    jti = uuid.uuid4().hex
    exp = datetime.now(timezone.utc) + timedelta(days=config.REFRESH_TOKEN_DAYS)
    await db.sessions.insert_one({"jti": jti, "user_id": user_id, "revoked": False, "expires_at": exp})
    return jwt.encode({"sub": user_id, "jti": jti, "exp": exp, "type": "refresh"}, config.JWT_SECRET, algorithm=ALGO)


def decode(token: str, kind: str) -> dict:
    try:
        payload = jwt.decode(token, config.JWT_SECRET, algorithms=[ALGO])
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Sesión expirada")
    except jwt.InvalidTokenError:
        raise HTTPException(401, "Token inválido")
    if payload.get("type") != kind:
        raise HTTPException(401, "Tipo de token inválido")
    return payload


@dataclass
class Ctx:
    user: dict
    perms: list
    is_global: bool
    institution_id: Optional[str]
    student_ids: Optional[list] = field(default=None)
    section_ids: Optional[list] = field(default=None)
    assignments: list = field(default_factory=list)
    teacher_id: Optional[str] = None

    @property
    def uid(self) -> str:
        return str(self.user["_id"])

    def scope(self) -> dict:
        return {"institution_id": self.institution_id} if self.institution_id else {}

    def require_institution(self) -> str:
        if not self.institution_id:
            raise HTTPException(400, "Seleccione una institución activa")
        return self.institution_id


async def get_ctx(request: Request) -> Ctx:
    token = request.cookies.get("access_token")
    auth = request.headers.get("Authorization", "")
    if not token and auth.startswith("Bearer "):
        token = auth[7:]
    if not token:
        raise HTTPException(401, "No autenticado")
    payload = decode(token, "access")
    user = await db.users.find_one({"_id": ObjectId(payload["sub"])})
    if not user or not user.get("is_active", True):
        raise HTTPException(401, "Usuario inactivo o inexistente")
    role = ROLES.get(user["role"], {})
    is_global = role.get("global", False)
    inst = (request.headers.get("X-Institution-Id") or None) if is_global else user.get("institution_id")
    student_ids = None
    if role.get("personal"):
        student_ids = await _personal_students(user)
    ctx = Ctx(user=user, perms=permissions_for(user["role"]), is_global=is_global, institution_id=inst, student_ids=student_ids)
    if user["role"] == "docente":
        teacher = await db.teachers.find_one({"user_id": str(user["_id"])})
        ctx.teacher_id = str(teacher["_id"]) if teacher else None
        ctx.assignments = await db.teacher_assignments.find({"teacher_id": ctx.teacher_id, "status": "activa"}).to_list(200) if teacher else []
        ctx.section_ids = sorted({a["section_id"] for a in ctx.assignments})
    return ctx


async def _personal_students(user: dict) -> list:
    if user["role"] == "estudiante":
        return [user["student_id"]] if user.get("student_id") else []
    guardian = await db.guardians.find_one({"_id": ObjectId(user["guardian_id"])}) if user.get("guardian_id") else None
    return guardian.get("student_ids", []) if guardian else []


def require(perm: str):
    async def dep(ctx: Ctx = Depends(get_ctx)) -> Ctx:
        if perm not in ctx.perms:
            raise HTTPException(403, f"Permiso requerido: {perm}")
        return ctx
    return dep


def check_institution(ctx: Ctx, doc: dict):
    if doc is None:
        raise HTTPException(404, "Registro no encontrado")
    if ctx.institution_id and doc.get("institution_id") != ctx.institution_id:
        raise HTTPException(404, "Registro no encontrado")
    if not ctx.is_global and not ctx.institution_id:
        raise HTTPException(403, "Usuario sin institución asignada")
