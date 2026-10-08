from datetime import datetime, timezone, timedelta
from typing import Literal, Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from erp.core import config
from erp.core.audit import audit
from erp.core.db import db
from erp.core.models import out
from erp.core.rbac import ROLES, MODULES, permissions_for
from erp.core.security import (Ctx, get_ctx, require, hash_password, verify_password, create_access_token,
                               create_refresh_token, decode)
from erp.shared.utils import now_iso, to_oid

router = APIRouter(prefix="/api")
MAX_ATTEMPTS, LOCK_MINUTES = 5, 15


class LoginIn(BaseModel):
    email: str
    password: str


class UserIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: str = Field(min_length=5, max_length=160)
    role: Literal[tuple(ROLES.keys())]
    password: Optional[str] = Field(default=None, min_length=8, max_length=128)
    is_active: bool = True
    guardian_id: Optional[str] = None
    student_id: Optional[str] = None


def client_ip(request: Request) -> str:
    fwd = request.headers.get("X-Forwarded-For", "")
    return fwd.split(",")[0].strip() if fwd else request.client.host


async def user_out(user: dict) -> dict:
    data = out(user)
    data["permissions"] = permissions_for(user["role"])
    data["role_label"] = ROLES.get(user["role"], {}).get("label", user["role"])
    data["is_global"] = ROLES.get(user["role"], {}).get("global", False)
    if user.get("institution_id"):
        inst = await db.institutions.find_one({"_id": ObjectId(user["institution_id"])})
        data["institution_name"] = inst["name"] if inst else None
    return data


def set_cookies(response: Response, access: str, refresh: str):
    opts = dict(httponly=True, secure=config.COOKIE_SECURE, samesite="lax", path="/")
    response.set_cookie("access_token", access, max_age=config.ACCESS_TOKEN_MINUTES * 60, **opts)
    response.set_cookie("refresh_token", refresh, max_age=config.REFRESH_TOKEN_DAYS * 86400, **opts)


@router.post("/auth/login")
async def login(body: LoginIn, request: Request, response: Response):
    email = body.email.strip().lower()
    ident = email
    ip = client_ip(request)
    now = datetime.now(timezone.utc)
    att = await db.login_attempts.find_one({"identifier": ident})
    if att and att.get("locked_until") and att["locked_until"].replace(tzinfo=timezone.utc) > now:
        raise HTTPException(429, "Demasiados intentos fallidos. Intente nuevamente en 15 minutos.")
    user = await db.users.find_one({"email": email})
    if not user or not verify_password(body.password, user["password_hash"]):
        count = (att or {}).get("count", 0) + 1
        upd = {"count": count, "last_at": now}
        if count >= MAX_ATTEMPTS:
            upd = {"count": 0, "locked_until": now + timedelta(minutes=LOCK_MINUTES)}
        await db.login_attempts.update_one({"identifier": ident}, {"$set": upd}, upsert=True)
        await db.audit_logs.insert_one({"institution_id": user.get("institution_id") if user else None, "user_email": email,
                                        "action": "login_failed", "entity": "auth", "ip": ip, "at": now_iso(), "details": {}})
        raise HTTPException(401, "Credenciales inválidas")
    if not user.get("is_active", True):
        raise HTTPException(403, "Usuario inactivo")
    await db.login_attempts.delete_one({"identifier": ident})
    uid = str(user["_id"])
    access, refresh = create_access_token(uid, email), await create_refresh_token(uid)
    set_cookies(response, access, refresh)
    await db.users.update_one({"_id": user["_id"]}, {"$set": {"last_login": now_iso()}})
    await db.audit_logs.insert_one({"institution_id": user.get("institution_id"), "user_id": uid, "user_email": email,
                                    "action": "login", "entity": "auth", "ip": ip, "at": now_iso(), "details": {}})
    return {"user": await user_out(user), "access_token": access}


@router.post("/auth/refresh")
async def refresh(request: Request, response: Response):
    token = request.cookies.get("refresh_token")
    if not token:
        raise HTTPException(401, "Sin token de renovación")
    payload = decode(token, "refresh")
    session = await db.sessions.find_one_and_update({"jti": payload["jti"], "revoked": False}, {"$set": {"revoked": True}})
    if not session:
        await db.sessions.update_many({"user_id": payload["sub"]}, {"$set": {"revoked": True}})
        raise HTTPException(401, "Token de renovación reutilizado o revocado")
    user = await db.users.find_one({"_id": ObjectId(payload["sub"])})
    if not user or not user.get("is_active", True):
        raise HTTPException(401, "Usuario inactivo")
    access, new_refresh = create_access_token(payload["sub"], user["email"]), await create_refresh_token(payload["sub"])
    set_cookies(response, access, new_refresh)
    return {"ok": True}


@router.post("/auth/logout")
async def logout(request: Request, response: Response):
    token = request.cookies.get("refresh_token")
    if token:
        try:
            await db.sessions.update_one({"jti": decode(token, "refresh")["jti"]}, {"$set": {"revoked": True}})
        except HTTPException:
            pass
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path="/")
    return {"ok": True}


@router.get("/auth/me")
async def me(ctx: Ctx = Depends(get_ctx)):
    return await user_out(ctx.user)


@router.get("/rbac/roles")
async def roles(ctx: Ctx = Depends(get_ctx)):
    return {"modules": MODULES, "roles": [{"key": k, "label": v["label"], "global": v.get("global", False), "permissions": v["perms"]}
                                          for k, v in ROLES.items()]}


def _guard_role(ctx: Ctx, role: str):
    if ROLES[role].get("global") and not ctx.is_global:
        raise HTTPException(403, "No puede asignar el rol de superadministrador")


@router.post("/users")
async def create_user(body: UserIn, request: Request, ctx: Ctx = Depends(require("users:create"))):
    _guard_role(ctx, body.role)
    if not body.password:
        raise HTTPException(422, "La contraseña es obligatoria (mínimo 8 caracteres)")
    email = body.email.strip().lower()
    if await db.users.find_one({"email": email}):
        raise HTTPException(409, "El correo ya está registrado")
    doc = body.model_dump(exclude={"password"})
    doc.update({"email": email, "password_hash": hash_password(body.password), "created_at": now_iso(),
                "institution_id": None if ROLES[body.role].get("global") else ctx.require_institution()})
    res = await db.users.insert_one(doc)
    await audit(ctx, "create", "users", res.inserted_id, {"email": email, "role": body.role}, ip=request.client.host)
    return await user_out(await db.users.find_one({"_id": res.inserted_id}))


@router.put("/users/{user_id}")
async def update_user(user_id: str, body: UserIn, request: Request, ctx: Ctx = Depends(require("users:update"))):
    oid = to_oid(user_id)
    user = await db.users.find_one({"_id": oid})
    if not user or (not ctx.is_global and user.get("institution_id") != ctx.institution_id):
        raise HTTPException(404, "Usuario no encontrado")
    _guard_role(ctx, body.role)
    if ROLES.get(user["role"], {}).get("global") and not ctx.is_global:
        raise HTTPException(403, "No puede modificar al superadministrador")
    if str(oid) == ctx.uid and (not body.is_active or body.role != user["role"]):
        raise HTTPException(409, "No puede desactivarse ni cambiar su propio rol")
    upd = body.model_dump(exclude={"password", "email"})
    if body.password:
        upd["password_hash"] = hash_password(body.password)
        await db.sessions.update_many({"user_id": user_id}, {"$set": {"revoked": True}})
    upd["updated_at"] = now_iso()
    await db.users.update_one({"_id": oid}, {"$set": upd})
    await audit(ctx, "update", "users", oid, {"role": body.role, "is_active": body.is_active, "password_changed": bool(body.password)},
                ip=request.client.host)
    return await user_out(await db.users.find_one({"_id": oid}))
