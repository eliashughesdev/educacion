# Test Credentials

Superadmin (global, todas las instituciones):
- eliasflotahughes@gmail.com / SchoolERP#2026!  (role: superadmin)

Demo users (password for all: Demo#2026!) — Institution "Colegio Horizonte del Saber" (CHS):
- admin.colegio@schoolerp.local (admin_institucional)
- director@schoolerp.local (director, read+export)
- secretaria@schoolerp.local (secretaria)
- cajero@schoolerp.local (cajero)
- contador@schoolerp.local (contador — can reverse payments)
- auditor@schoolerp.local (auditor, read-only)
- docente@schoolerp.local (docente — titular of "1ro de Primaria A" Sede Central; P1 grades seeded, Educación Artística P1 left in borrador)
- tutor@schoolerp.local (tutor — sees only linked dependents)
- estudiante@schoolerp.local (estudiante — sees only self)
Institution "Instituto Bilingüe Costa Azul" (IBCA):
- admin.costa@schoolerp.local (admin_institucional)

Auth endpoints: POST /api/auth/login, POST /api/auth/refresh, POST /api/auth/logout, GET /api/auth/me
Reset demo data (dev only): cd /app/backend && python -m erp.seed --reset
