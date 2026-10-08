from erp.core.db import db
from erp.shared.utils import now_iso


async def audit(ctx, action: str, entity: str, entity_id=None, details=None, institution_id=None, ip=None):
    user = ctx.user if ctx else {}
    await db.audit_logs.insert_one({
        "institution_id": institution_id or (ctx.institution_id if ctx else None) or user.get("institution_id"),
        "user_id": str(user.get("_id")) if user else None,
        "user_email": user.get("email", "sistema"),
        "action": action,
        "entity": entity,
        "entity_id": str(entity_id) if entity_id else None,
        "details": details or {},
        "ip": ip,
        "at": now_iso(),
    })
