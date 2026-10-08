# Arquitectura — School ERP Enterprise (Bloque 1)

## Monolito modular
```
backend/
  server.py                 # FastAPI app, routers, startup (índices + seed)
  erp/core/                 # config, db, models (BaseDocument/PyObjectId), security (JWT, Ctx, require), rbac, audit
  erp/shared/               # exporters (PDF/XLSX/CSV/JSON/DOCX/HTML-print), utils
  erp/modules/              # auth, crud (genérico), registry (entidades), students, enrollments, finance(+service), dashboard, reports
  erp/infrastructure/       # sqlserver_models.py (SQLAlchemy 2.x, objetivo SQL Server)
  erp/seed.py               # seed admin + demo reproducible (random.Random(2026))
database/ schema/ procedures/   # T-SQL objetivo
frontend/src/
  components/{layout,common,finance,academic}/  pages/  context/  hooks/  lib/
```

## Decisiones
- **Registro de entidades** (`registry.py`): cada entidad declara colección, permisos, columnas, búsqueda, filtros, unicidad, referencias y bloqueos de borrado. Lo usan listado, CRUD y exportación → mismos filtros y permisos en pantalla y en reportes.
- **Alcance**: `Ctx` resuelve institución (fija para usuarios de institución; selector `X-Institution-Id` solo para superadmin) y dependientes (tutor/estudiante). Todas las consultas aplican el alcance en servidor.
- **Integridad**: cupo con `find_one_and_update` condicional (`enrolled_count < capacity`); índice único parcial de matrícula activa por año; pagos con clave de idempotencia única + actualización condicional del saldo; caja única abierta por cajero (índice parcial); anulación solo sin pagos; reverso con separación de funciones.
- **Sesiones**: access token 30 min + refresh 7 días en cookies httpOnly (SameSite=Lax), rotación con detección de reutilización, bloqueo tras 5 intentos.
- **Exportación**: un motor único genera los 6 formatos para listados, factura, recibo, estado de cuenta y arqueo; cada exportación se audita.

## Desviaciones conocidas respecto al prompt maestro
- Frontend en React (CRA + JavaScript) de la plantilla del entorno, no Vite + TypeScript.
- Motor en ejecución: MongoDB (decisión del cliente para la vista previa). SQL Server entregado como scripts + modelos, sin ejecutar.
- Hash de contraseñas con bcrypt (no Argon2id); MFA, Redis, workers y WebSockets pendientes.
