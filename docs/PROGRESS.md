# PROGRESS — School ERP Enterprise

| Módulo | Estado |
|---|---|
| Identidad: login JWT, refresh rotativo, logout, bloqueo por intentos, usuarios, RBAC 10 roles | Implementado |
| M01 Instituciones, sedes, años, períodos | Implementado |
| M04 Grados, secciones, cupos | Implementado |
| M02/M03 Estudiantes, tutores, vínculos, matrícula, cambio de sección, retiro | Implementado |
| M10 Tarifas, facturas (individual/masiva/anulación), caja (apertura/cierre/arqueo), pagos (idempotentes, reverso), CxC antigüedad, estado de cuenta | Implementado |
| Dashboard centro de mando con KPIs reales y drill-down | Implementado |
| Reportes / exportación PDF, XLSX, CSV, JSON, DOCX, impresión | Implementado |
| M26 Auditoría | Implementado |
| Esquema SQL Server + SPs + modelos SQLAlchemy | Desarrollo (no ejecutado en SQL Server) |
| Complemento MINERD: docentes, asignaciones (titular/asignatura/sustituto) con control de choques, cobertura docente | Implementado |
| Registro de notas P1-P4 por competencias, borrador/publicación/bloqueo, solicitudes de corrección con aprobación | Implementado |
| Asistencia/observaciones por período, boletín plegable PDF + otros formatos, aprobación docente/dirección versionada | Implementado |
| Conformidad con plantilla oficial MINERD vigente | Pendiente de validación oficial |
| Firma digital certificada, QR de verificación, lotes en segundo plano, reservas de cupo / lista de espera | Pendiente |
| MFA, Argon2id, Redis, workers, WebSockets | Pendiente |
| M05-M09, M11-M25 | Pendiente |
