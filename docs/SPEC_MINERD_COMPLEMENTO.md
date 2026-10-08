# SCHOOL ERP ENTERPRISE — COMPLEMENTO FUNCIONAL
## Gestión docente, cupos escolares, registro de calificaciones MINERD y boletín plegable

> **Alcance:** Este documento **complementa** el prompt maestro original. Implementar exclusivamente los requerimientos nuevos y las integraciones necesarias, sin reescribir ni duplicar módulos ya funcionales. Conservar FastAPI, React/TypeScript y Microsoft SQL Server.

## 1. Gestión avanzada de docentes y titularidad de aulas

Crear o completar el **módulo de maestros** con expediente profesional, estado laboral, especialidad, niveles y asignaturas habilitadas, disponibilidad, carga horaria, horario semanal, sustituciones y trazabilidad de asignaciones. Una asignación docente deberá asociar de forma explícita **institución, sede, año escolar, nivel, grado, sección/aula, asignatura, función (titular o docente de asignatura), fechas de vigencia y estado**.

- Permitir designar **maestro titular por sección**, docentes de asignaturas, sustitutos y coordinador responsable, con historial de cambios.
- No permitir asignaciones solapadas de un mismo docente cuando los horarios se superponen; controlar también doble ocupación del aula.
- Disponer de vista «Mis secciones», lista de alumnos, horario, asistencia, registro de notas, alertas y boletines pendientes.
- Dar a dirección/coordinación autorización para asignar o reemplazar docentes; los maestros solamente editan los registros académicos de las secciones y asignaturas que les corresponden.
- Incorporar carga docente, filtros por año/sección, disponibilidad, incidencias y reporte de cobertura docente.

## 2. Matrícula vinculada a secciones y control estricto de cupos

Cada estudiante matriculado debe estar vinculado a **un grado y sección concreta durante un año académico**, con histórico de traslados, cambios de sección, retiro y reinscripción. Gestionar **capacidad autorizada por aula/sección**, ocupación efectiva, cupos reservados y disponibles; mostrar en tiempo real «inscritos / capacidad», porcentaje de ocupación y alertas por sobrecupo.

- Validar matrícula y cambio de sección dentro de una **transacción SQL Server**, bloqueando carreras de concurrencia que puedan superar el cupo.
- Rechazar inscripciones adicionales cuando no existan cupos, salvo un flujo excepcional de autorización expresa y auditable conforme a política institucional.
- No contar estudiantes retirados como activos; definir claramente el efecto de preinscripciones y reservas pendientes en cupos disponibles.
- Exponer desde cursos y matrícula una lista filtrable con docentes, estudiantes asignados, vacantes y lista de espera; permitir traslado de sección con control de conflictos y trazabilidad.
- Incluir indicadores clicables de ocupación por aula, secciones al límite, sobrecupo autorizado y pendientes de asignación.

## 3. Registro de calificaciones docente conforme al MINERD

Implementar **registro de notas virtual**, configurable por nivel, grado, asignatura, año escolar y versión del instrumento oficial aplicable del **Ministerio de Educación de la República Dominicana (MINERD)**. No imponer una fórmula universal: verificar normativa e instrumentos oficiales vigentes antes de codificar escalas, competencias, ponderaciones, reglas de recuperación, promoción y criterios de cierre.

- Disponer de **P1, P2, P3 y P4**, áreas curriculares, competencias fundamentales/específicas, indicadores de logro y calificaciones por competencia **cuando corresponda al nivel y formato oficial**.
- Mantener actividades/evidencias evaluativas, rúbricas, ponderaciones autorizadas, observaciones por período, asistencia y ausencias, con cálculos reproducibles y trazables.
- Permitir captura individual y por cuadrícula, autoguardado seguro, validación, borradores, revisión, aprobación, publicación y bloqueo por período.
- Corregir notas publicadas solo mediante solicitud/autorización, con motivo y bitácora del valor anterior y nuevo.
- Mostrar al docente vista previa del boletín y las inconsistencias que impiden su publicación (campos obligatorios, notas fuera de escala, registros incompletos).
- Al cambiar de curso o estudiante, cargar siempre datos autorizados de ese contexto; prohibir mezclar notas entre estudiantes, períodos o secciones.

## 4. Boletín / volante de notas plegable con portada dinámica

Crear un **generador de informe de aprendizaje plegable**, con vista previa multipágina y salida PDF lista para **impresión, doblado y entrega física**, basado en el formato oficial MINERD que corresponda a cada nivel. La imagen de referencia facilitada es una guía visual; confirmar dimensiones, orientación, orden de paneles, escala y campos con la plantilla oficial vigente. Preservar un motor de plantillas versionadas por nivel y año escolar.

### Portada vinculada al estudiante

Actualizar automáticamente, al seleccionar otro estudiante:
- Nombre(s), apellido(s), código/ID del estudiante autorizado y número de orden.
- Centro educativo, sede, distrito/regional cuando aplique, año escolar, nivel, grado y sección.
- Docente titular, director/a vigente, identidad visual institucional y nombre del documento.
- Datos adicionales obligatorios previstos en la plantilla oficial.

**No generar portadas estáticas:** las selecciones deben recuperar en backend las relaciones reales entre matrícula, estudiante, sección, docente titular y dirección; respetar RBAC.

### Interior y reverso: campos completos

Reproducir fielmente los bloques que exija el formato correspondiente, incluyendo cuando aplique:
- Cuadrícula de áreas curriculares y competencias, columnas P1–P4 y calificaciones finales / competencias específicas.
- Observaciones pedagógicas individualizadas para los cuatro períodos.
- Resumen de asistencia, ausencias y porcentajes por período y anual.
- Leyenda de períodos, competencias y escala de valoración oficial.
- Espacios de firmas o constancias de recepción de padre, madre o tutor legal.
- Recomendaciones de apoyo para el aprendizaje.
- Datos de promoción/cierre y validaciones oficiales exigidas para el nivel.

Todos los campos obligatorios deben ser dinámicos o tener tratamiento explícito de «pendiente/no aplica» según norma; **nunca inventar notas, observaciones ni firmas**.

### Firma del docente titular y director/a

- Registrar la identidad y vigencia del **maestro titular de la sección** y **director/a del centro** asociados al período de emisión.
- Implementar workflow «borrador → revisión → aprobación docente → validación de dirección → emisión» con sello de tiempo, usuario, versión del boletín y evidencia de aprobación.
- Incluir espacios de firma imprimibles y, si existe integración válida, firma electrónica/digital verificable. **Una imagen de rúbrica pegada en PDF no constituye por sí misma una firma digital legalmente válida**.
- Nunca firmar automáticamente en nombre de una persona sin autorización y un método de firma aprobado. Si falta la aprobación requerida, presentar «Pendiente de firma» y bloquear la emisión oficial.
- Mantener expediente de emisiones, descargas, anulaciones y reemisiones; opcionalmente QR de verificación sin exponer datos privados públicamente.

### Impresión y exportación

- PDF con fuentes incrustadas, márgenes, saltos de página, tamaño de papel, orientación, **orden de caras/paneles para plegado** y opción de impresión a doble cara configurados.
- Vista previa del exterior e interior; prueba de impresión al 100 % sin cortes ni superposiciones.
- Exportación individual y masiva por sección, solo para usuarios con permisos específicos; procesar lotes en segundo plano.

## 5. Modelo SQL Server y controles de integridad adicionales

Ampliar el esquema actual con entidades equivalentes, únicamente donde falten: `TeacherAssignments`, `HomeroomAssignments`, `SectionCapacity`, `SectionSeatReservations`, `EnrollmentSectionHistory`, `AssessmentRubrics`, `CompetencyGrades`, `GradeRevisionRequests`, `ReportCardTemplates`, `ReportCardVersions`, `ReportCardApprovals`, `ReportCardSignatures`, `ReportCardIssuances` y `ReportCardPrintJobs`.

Establecer relaciones, índices compuestos para estudiante/año/sección y docente/año/sección/asignatura, restricciones de unicidad, integridad de vigencias, auditoría y control de concurrencia. Implementar procedimientos transaccionales para asignación/movimiento de cupos y cierre/publicación de notas **solo donde resulte técnicamente justificado**. No almacenar archivos PDF grandes dentro de tablas transaccionales si existe almacenamiento documental seguro.

## 6. Flujos que deben funcionar de extremo a extremo

1. Dirección crea un grado/sección y establece su capacidad real.
2. Asigna un maestro titular y los profesores por asignatura; se comprueban conflictos.
3. Secretaría matricula estudiantes y ve vacantes actualizadas; el sistema impide sobrepasar el cupo en matrículas concurrentes.
4. El docente inicia sesión y ve exclusivamente sus aulas, estudiantes y registros habilitados.
5. Completa notas/competencias, asistencia y observaciones del período, con validación oficial por plantilla vigente.
6. Dirección revisa y aprueba el volante correspondiente al estudiante.
7. El sistema genera portada e interior personalizados, recoge aprobaciones/firmas válidas y exporta el boletín plegable PDF.
8. Se cambia el estudiante seleccionado y **todos** los campos (portada, notas, asistencia, observaciones y firmantes según vigencia) se actualizan, sin datos residuales del anterior.
9. El padre o tutor autorizado consulta/descarga el documento publicado, y queda registro de acceso.

## 7. Pruebas y criterios de aceptación obligatorios

- Probar ocupación **exactamente igual a capacidad** y dos inscripciones simultáneas compitiendo por el último cupo.
- Probar reasignaciones, retiros, reservas vencidas y cambios de docente titular a mitad del año.
- Probar que un docente no pueda editar otra sección, ni otro período cerrado, ni notas publicadas sin autorización.
- Probar diferentes niveles, instrumentos y años académicos sin asumir el mismo esquema de notas para todos.
- Comparar el PDF generado visualmente con la plantilla oficial aplicable; verificar campos, paginado, legibilidad, impresión plegable y firmas.
- Confirmar que el cambio de alumno regenera todos los datos del boletín y que ninguna sesión accede a información ajena.
- Implementar pruebas automatizadas backend, SQL Server, frontend y E2E; informar qué se ejecutó y qué quedó bloqueado por falta de normativa, plantillas o certificados.

## 8. Instrucción al agente

**Implementa este complemento sin repetir el plan maestro.** Antes de programar, inspecciona los módulos ya existentes de estudiantes, matrículas, estructura académica, docentes y calificaciones. Identifica únicamente brechas y archivos afectados; después realiza cambios integrados, compila, ejecuta migraciones seguras y presenta pruebas verificables. Si no dispones de la **normativa MINERD vigente y la plantilla oficial** correspondiente al nivel educativo, implementa el motor configurable y la interfaz, pero marca la conformidad oficial como **pendiente de validación**, sin afirmar cumplimiento normativo.
