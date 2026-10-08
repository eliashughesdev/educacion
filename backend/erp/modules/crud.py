import re

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import ValidationError

from erp.core.audit import audit
from erp.core.db import db
from erp.core.models import out
from erp.core.security import Ctx, get_ctx, check_institution
from erp.modules.registry import ENTITIES
from erp.shared.utils import now_iso, to_oid, next_seq

router = APIRouter(prefix="/api")


def cfg_of(entity: str) -> dict:
    if entity not in ENTITIES:
        raise HTTPException(404, "Recurso no encontrado")
    return ENTITIES[entity]


def need(ctx: Ctx, cfg: dict, action: str):
    perm = f"{cfg['perm']}:{action}"
    if perm not in ctx.perms:
        raise HTTPException(403, f"Permiso requerido: {perm}")


async def build_query(entity: str, cfg: dict, ctx: Ctx, params: dict) -> dict:
    q = dict(cfg.get("base", {}))
    if not ctx.is_global and not ctx.institution_id:
        raise HTTPException(403, "Usuario sin institución asignada")
    if cfg.get("scoped", True):
        q.update(ctx.scope())
    elif entity == "institutions" and ctx.institution_id:
        q["_id"] = ObjectId(ctx.institution_id)
    if ctx.student_ids is not None:
        field = cfg.get("personal")
        if not field:
            raise HTTPException(403, "Acceso restringido")
        ids = [ObjectId(i) for i in ctx.student_ids] if field == "_id" else ctx.student_ids
        q[field] = {"$in": ids}
    if ctx.section_ids is not None and cfg.get("section_field"):
        sf = cfg["section_field"]
        q[sf] = {"$in": [ObjectId(i) for i in ctx.section_ids] if sf == "_id" else ctx.section_ids}
    text = (params.get("q") or "").strip()
    if text and cfg.get("search"):
        q["$or"] = [{f: {"$regex": re.escape(text), "$options": "i"}} for f in cfg["search"]]
    for f in cfg.get("filters", []):
        if params.get(f) not in (None, "", "all"):
            q[f] = params[f]
    df = cfg.get("date_field")
    if df and (params.get("date_from") or params.get("date_to")):
        rng = {}
        if params.get("date_from"):
            rng["$gte"] = params["date_from"]
        if params.get("date_to"):
            rng["$lte"] = params["date_to"] + "T23:59:59"
        q[df] = rng
    if cfg.get("custom"):
        cfg["custom"](q, params)
    return q


def sort_spec(cfg: dict, params: dict):
    s = params.get("sort") or cfg.get("sort", "_id")
    return [(s.lstrip("-"), -1 if s.startswith("-") else 1)]


async def fetch_rows(entity: str, cfg: dict, ctx: Ctx, params: dict, skip=0, limit=50000):
    q = await build_query(entity, cfg, ctx, params)
    docs = await db[cfg["coll"]].find(q).sort(sort_spec(cfg, params)).skip(skip).limit(limit).to_list(limit)
    rows = [out(d) for d in docs]
    return (cfg["post"](rows) if cfg.get("post") else rows), q


def validate(cfg: dict, data: dict) -> dict:
    try:
        return cfg["schema"](**data).model_dump(mode="json")
    except ValidationError as e:
        raise HTTPException(422, [{"loc": list(err["loc"]), "msg": err["msg"]} for err in e.errors()])


async def ensure_unique(cfg: dict, data: dict, exclude_id=None):
    for fields in cfg.get("unique", []):
        if any(not data.get(f) for f in fields):
            continue
        q = {f: data[f] for f in fields}
        if cfg.get("scoped", True):
            q["institution_id"] = data.get("institution_id")
        if exclude_id:
            q["_id"] = {"$ne": exclude_id}
        if await db[cfg["coll"]].find_one(q):
            raise HTTPException(409, f"Ya existe un registro con el mismo valor en: {', '.join(fields)}")


async def enrich(cfg: dict, data: dict, ctx: Ctx, exclude_id=None):
    for key, (coll, field, target) in {**cfg.get("refs", {})}.items():
        if not data.get(key):
            data[target] = None
            continue
        ref = await db[coll].find_one({"_id": to_oid(data[key])})
        if not ref or ref.get("institution_id") != data.get("institution_id"):
            raise HTTPException(422, f"Referencia inválida: {key}")
        data[target] = ref.get(field)
    for key, coll, field, target in cfg.get("extra_refs", []):
        ref = await db[coll].find_one({"_id": to_oid(data[key])}) if data.get(key) else None
        data[target] = ref.get(field) if ref else None
    if cfg.get("validate"):
        await cfg["validate"](data, exclude_id)


async def after_save(entity: str, data: dict, oid):
    if entity == "academic-years" and data.get("is_current"):
        await db.academic_years.update_many({"institution_id": data["institution_id"], "_id": {"$ne": oid}}, {"$set": {"is_current": False}})


@router.get("/{entity}")
async def list_entity(entity: str, request: Request, page: int = 1, limit: int = 25, ctx: Ctx = Depends(get_ctx)):
    cfg = cfg_of(entity)
    need(ctx, cfg, "view")
    params = dict(request.query_params)
    limit = max(1, min(limit, 500))
    rows, q = await fetch_rows(entity, cfg, ctx, params, skip=(max(page, 1) - 1) * limit, limit=limit)
    total = await db[cfg["coll"]].count_documents(q)
    return {"items": rows, "total": total, "page": page, "limit": limit}


@router.get("/{entity}/{item_id}")
async def get_entity(entity: str, item_id: str, ctx: Ctx = Depends(get_ctx)):
    cfg = cfg_of(entity)
    need(ctx, cfg, "view")
    q = await build_query(entity, cfg, ctx, {})
    q["_id"] = to_oid(item_id)
    doc = await db[cfg["coll"]].find_one(q)
    if not doc:
        raise HTTPException(404, "Registro no encontrado")
    return out(doc)


@router.post("/{entity}")
async def create_entity(entity: str, payload: dict, request: Request, ctx: Ctx = Depends(get_ctx)):
    cfg = cfg_of(entity)
    if cfg.get("readonly"):
        raise HTTPException(405, "Operación no permitida")
    need(ctx, cfg, "create")
    if cfg.get("global_write") and not ctx.is_global:
        raise HTTPException(403, "Solo el superadministrador puede crear este recurso")
    data = validate(cfg, payload)
    if cfg.get("scoped", True):
        data["institution_id"] = ctx.require_institution()
    await ensure_unique(cfg, data)
    await enrich(cfg, data, ctx)
    if cfg.get("computed"):
        cfg["computed"](data)
    if cfg.get("seq"):
        inst = await db.institutions.find_one({"_id": ObjectId(data["institution_id"])})
        data["code"] = f"{inst['code']}-{await next_seq(cfg['seq'] + ':' + data['institution_id']):05d}"
    data.update(cfg.get("defaults", {}))
    data.update({"created_at": now_iso(), "created_by": ctx.uid})
    res = await db[cfg["coll"]].insert_one(data)
    await after_save(entity, data, res.inserted_id)
    await audit(ctx, "create", entity, res.inserted_id, {"name": data.get("name") or data.get("full_name")}, ip=request.client.host)
    return out(await db[cfg["coll"]].find_one({"_id": res.inserted_id}))


@router.put("/{entity}/{item_id}")
async def update_entity(entity: str, item_id: str, payload: dict, request: Request, ctx: Ctx = Depends(get_ctx)):
    cfg = cfg_of(entity)
    if cfg.get("readonly"):
        raise HTTPException(405, "Operación no permitida")
    need(ctx, cfg, "update")
    oid = to_oid(item_id)
    doc = await db[cfg["coll"]].find_one({"_id": oid})
    if cfg.get("scoped", True):
        check_institution(ctx, doc)
    elif doc is None or (ctx.institution_id and str(doc["_id"]) != ctx.institution_id):
        raise HTTPException(404, "Registro no encontrado")
    fields = cfg["schema"].model_fields.keys()
    merged = {k: doc.get(k) for k in fields if doc.get(k) is not None}
    merged.update({k: v for k, v in payload.items() if k in fields})
    data = validate(cfg, merged)
    if cfg.get("scoped", True):
        data["institution_id"] = doc["institution_id"]
    if entity == "sections" and data["capacity"] < doc.get("enrolled_count", 0):
        raise HTTPException(409, "La capacidad no puede ser menor que los inscritos actuales")
    await ensure_unique(cfg, data, exclude_id=oid)
    await enrich(cfg, data, ctx, exclude_id=oid)
    if cfg.get("computed"):
        cfg["computed"](data)
    data.update({"updated_at": now_iso(), "updated_by": ctx.uid})
    await db[cfg["coll"]].update_one({"_id": oid}, {"$set": data})
    await after_save(entity, data, oid)
    changes = {k: {"antes": doc.get(k), "despues": v} for k, v in data.items() if doc.get(k) != v and k not in ("updated_at", "updated_by")}
    await audit(ctx, "update", entity, oid, changes, ip=request.client.host)
    return out(await db[cfg["coll"]].find_one({"_id": oid}))


@router.delete("/{entity}/{item_id}")
async def delete_entity(entity: str, item_id: str, request: Request, ctx: Ctx = Depends(get_ctx)):
    cfg = cfg_of(entity)
    if cfg.get("readonly"):
        raise HTTPException(405, "Operación no permitida")
    need(ctx, cfg, "delete")
    if cfg.get("global_write") and not ctx.is_global:
        raise HTTPException(403, "Solo el superadministrador puede eliminar este recurso")
    oid = to_oid(item_id)
    doc = await db[cfg["coll"]].find_one({"_id": oid})
    if cfg.get("scoped", True):
        check_institution(ctx, doc)
    elif doc is None:
        raise HTTPException(404, "Registro no encontrado")
    for coll, field in cfg.get("block", []):
        if await db[coll].find_one({field: item_id}):
            raise HTTPException(409, "No se puede eliminar: el registro está en uso. Inactívelo en su lugar.")
    await db[cfg["coll"]].delete_one({"_id": oid})
    await audit(ctx, "delete", entity, oid, {"snapshot": out(doc)}, ip=request.client.host)
    return {"ok": True}
