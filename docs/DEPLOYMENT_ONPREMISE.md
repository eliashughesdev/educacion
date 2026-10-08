# Guía de despliegue On-Premise — School ERP Enterprise

> Estado: Bloque 1 (Fases 0-1 + identidad, institucional, académico base, estudiantes, matrícula, facturación, caja, cuentas por cobrar, reportes y auditoría).

## 1. Credenciales iniciales (cámbielas tras el primer acceso)

| Cuenta | Usuario | Contraseña | Origen |
|---|---|---|---|
| **Superadministrador** | `eliasflotahughes@gmail.com` | `SchoolERP#2026!` | `backend/.env` → `ADMIN_EMAIL` / `ADMIN_PASSWORD` (creado por `backend/erp/seed.py → seed_admin`) |
| Usuarios demo (todos los roles) | ver tabla abajo | `Demo#2026!` | `backend/.env` → `DEMO_PASSWORD` (creados por `seed_demo`) |

Usuarios demo (`SEED_DEMO_DATA="true"`):
`admin.colegio@schoolerp.local` (Admin institucional), `director@`, `secretaria@`, `cajero@`, `contador@`, `auditor@`, `docente@`, `tutor@`, `estudiante@` — todos `@schoolerp.local` — y `admin.costa@schoolerp.local` (segunda institución, para probar aislamiento).

- Al iniciar, el backend **crea o re-sincroniza** el superadministrador con los valores del `.env`. Para cambiar la clave: edite `ADMIN_PASSWORD` y reinicie el servicio.
- En producción: `SEED_DEMO_DATA="false"`, `APP_ENV="production"` (bloquea `--reset`), nuevo `JWT_SECRET` (`python -c "import secrets;print(secrets.token_hex(32))"`).

## 2. Topología recomendada

```
[Clientes] --HTTPS--> [IIS 10 (Windows Server 2022)]
                         ├─ /        → frontend/build (sitio estático + URL Rewrite a index.html)
                         └─ /api/*   → ARR reverse proxy → http://127.0.0.1:8001 (FastAPI/Uvicorn como servicio Windows - NSSM)
                                                     └─ SQL Server 2019+/2022 (objetivo) · MongoDB 7 (motor actual de ejecución)
```

## 3. Requisitos
- Windows Server 2019/2022, IIS 10 con **URL Rewrite** y **Application Request Routing (ARR)**.
- Python 3.11 x64, Node.js 20 LTS + Yarn 1.22.
- Base de datos: **MongoDB 7 Community** (motor con el que este bloque fue ejecutado y probado) y **SQL Server 2019+** con **ODBC Driver 18** para el esquema objetivo (`database/`).
- NSSM (https://nssm.cc) para registrar Uvicorn como servicio.

## 4. Backend (FastAPI)
```powershell
cd C:\SchoolERP\backend
py -3.11 -m venv .venv ; .\.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env   # o edite .env con los valores de la sección 5
python -m erp.seed       # crea índices, superadmin y (opcional) datos demo
nssm install SchoolERP-API "C:\SchoolERP\backend\.venv\Scripts\uvicorn.exe" "server:app --host 127.0.0.1 --port 8001 --workers 4"
nssm set SchoolERP-API AppDirectory C:\SchoolERP\backend
nssm start SchoolERP-API
```
Reiniciar datos demo (solo desarrollo): `python -m erp.seed --reset`.

## 5. Variables de entorno (`backend/.env`)
| Variable | Descripción |
|---|---|
| `MONGO_URL`, `DB_NAME` | Conexión del motor actual |
| `CORS_ORIGINS` | Origen(es) permitidos, p.ej. `https://erp.colegio.local` |
| `APP_ENV` | `development` / `production` |
| `JWT_SECRET` | Secreto HS256 (64 hex) |
| `ACCESS_TOKEN_MINUTES`, `REFRESH_TOKEN_DAYS` | Vida de tokens (30 min / 7 días) |
| `COOKIE_SECURE` | `true` con HTTPS |
| `ADMIN_EMAIL`, `ADMIN_PASSWORD` | Superadministrador |
| `DEMO_PASSWORD`, `SEED_DEMO_DATA` | Datos de demostración |

## 6. Frontend
```powershell
cd C:\SchoolERP\frontend
# .env → REACT_APP_BACKEND_URL=https://erp.colegio.local
yarn install ; yarn build
```
Publique `frontend\build` como sitio IIS. `web.config`:
```xml
<configuration><system.webServer><rewrite><rules>
  <rule name="api" stopProcessing="true"><match url="^api/(.*)" /><action type="Rewrite" url="http://127.0.0.1:8001/api/{R:1}" /></rule>
  <rule name="spa" stopProcessing="true"><match url=".*" />
    <conditions logicalGrouping="MatchAll"><add input="{REQUEST_FILENAME}" matchType="IsFile" negate="true" /></conditions>
    <action type="Rewrite" url="/index.html" /></rule>
</rules></rewrite></system.webServer></configuration>
```
Habilite el proxy en ARR (Server Proxy Settings → Enable proxy) y vincule un certificado TLS al sitio.

## 7. SQL Server (esquema objetivo)
```powershell
sqlcmd -S SQLHOST -E -Q "CREATE DATABASE SchoolERP"
sqlcmd -S SQLHOST -E -d SchoolERP -i database\schema\001_core_schema.sql
sqlcmd -S SQLHOST -E -d SchoolERP -i database\schema\002_minerd_teachers_report_cards.sql
sqlcmd -S SQLHOST -E -d SchoolERP -i database\procedures\sp_EnrollStudent.sql
sqlcmd -S SQLHOST -E -d SchoolERP -i database\procedures\sp_ApplyPayment.sql
```
Modelos SQLAlchemy equivalentes: `backend/erp/infrastructure/sqlserver_models.py`.
**Importante:** en este bloque los scripts T-SQL y los modelos SQLAlchemy se entregan pero **no fueron ejecutados** contra un SQL Server real (el entorno de vista previa no lo permite). El adaptador de repositorio SQL Server es el siguiente bloque.

## 8. Respaldo y recuperación
- MongoDB: `mongodump --uri "%MONGO_URL%" --db SchoolERP --gzip --archive=D:\backups\erp-%DATE%.gz` diario (Programador de tareas) + prueba mensual de `mongorestore`.
- SQL Server: completo semanal, diferencial diario, log cada 15 min (modelo FULL).

## 9. Verificación post-despliegue
1. `GET https://erp.colegio.local/api/health` → `{"status":"ok"}`
2. Documentación OpenAPI: `https://erp.colegio.local/api/docs`
3. Inicie sesión con el superadministrador y cambie la contraseña.
