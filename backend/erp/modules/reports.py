from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Request

from erp.core.audit import audit
from erp.core.db import db
from erp.core.security import Ctx, get_ctx
from erp.modules.crud import cfg_of, fetch_rows
from erp.modules.registry import ENTITIES
from erp.shared.exporters import export_response
from erp.shared.utils import money

router = APIRouter(prefix="/api/reports")


@router.get("/catalog")
async def catalog(ctx: Ctx = Depends(get_ctx)):
    return [{"key": k, "title": c["title"], "filters": c.get("filters", []), "date_filter": bool(c.get("date_field"))}
            for k, c in ENTITIES.items() if f"{c['perm']}:export" in ctx.perms]


@router.get("/{key}/export")
async def export(key: str, request: Request, format: str = "pdf", ctx: Ctx = Depends(get_ctx)):
    cfg = cfg_of(key)
    if f"{cfg['perm']}:export" not in ctx.perms:
        raise HTTPException(403, f"Permiso requerido: {cfg['perm']}:export")
    params = dict(request.query_params)
    rows, _ = await fetch_rows(key, cfg, ctx, params)
    inst = await db.institutions.find_one({"_id": ObjectId(ctx.institution_id)}) if ctx.institution_id else None
    filters = {k: v for k, v in params.items() if k not in ("format",) and v}
    meta = [("Institución", inst["name"] if inst else "Todas las instituciones"), ("Generado por", ctx.user["email"]),
            ("Registros", len(rows)), ("Filtros", ", ".join(f"{k}={v}" for k, v in filters.items()) or "Ninguno")]
    totals = [(f"Total {dict(cfg['cols']).get(f, f)}", money(sum(r.get(f) or 0 for r in rows))) for f in cfg.get("sum", [])]
    await audit(ctx, "export", key, None, {"format": format, "rows": len(rows), "filters": filters}, ip=request.client.host)
    return export_response(format, f"{key}", cfg["title"], cfg["cols"], rows, meta, totals)
