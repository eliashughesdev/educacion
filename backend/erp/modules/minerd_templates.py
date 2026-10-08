"""Plantillas de informe de aprendizaje (motor configurable). Conformidad oficial MINERD: PENDIENTE DE VALIDACIÓN."""

COMP_3 = [
    {"key": "C1", "name": "Comunicativa"},
    {"key": "C2", "name": "Pensamiento Lógico, Creativo y Crítico; Resolución de Problemas; Científica y Tecnológica"},
    {"key": "C3", "name": "Ética y Ciudadana; Desarrollo Personal y Espiritual; Ambiental y de la Salud"},
]
PERIODS = [{"key": "P1", "months": "Ago-Sept-Oct"}, {"key": "P2", "months": "Nov-Dic-Ene"},
           {"key": "P3", "months": "Feb-Mar"}, {"key": "P4", "months": "Abr-May-Jun"}]
SCALE_NUM = [
    {"min": 89, "max": 100, "label": "Destacado", "description": "Evidencia un desempeño destacado en los aspectos evaluados de las competencias de cada área."},
    {"min": 77, "max": 88, "label": "Logrado", "description": "Evidencia que ha logrado, en general, los aprendizajes esperados en las competencias de cada área."},
    {"min": 65, "max": 76, "label": "En proceso", "description": "Evidencia que aún se encuentra en proceso respecto a los aspectos evaluados, mostrando un logro muy básico."},
    {"min": 0, "max": 64, "label": "Insuficiente", "description": "Evidencia un desempeño insuficiente en los aspectos evaluados de las competencias de cada área."},
]
VALIDATION = "Pendiente de validación contra la plantilla oficial MINERD vigente"

TEMPLATES = [
    {"key": "MINERD-INI", "version": "2026.1", "name": "Informe de Aprendizaje · Nivel Inicial", "level": "inicial", "orders": [],
     "scale_type": "qualitative", "values": [{"key": "L", "label": "Logrado"}, {"key": "EP", "label": "En proceso"}, {"key": "I", "label": "Iniciado"}],
     "competencies": COMP_3, "periods": PERIODS, "scale": [], "pass_mark": None, "official_validation": VALIDATION},
    {"key": "MINERD-PRI-1C", "version": "2026.1", "name": "Informe de Aprendizaje · Primer Ciclo Nivel Primario", "level": "primaria", "orders": [1, 2, 3],
     "scale_type": "numeric", "min": 0, "max": 100, "pass_mark": 65, "competencies": COMP_3, "periods": PERIODS, "scale": SCALE_NUM,
     "official_validation": VALIDATION},
    {"key": "MINERD-PRI-2C", "version": "2026.1", "name": "Informe de Aprendizaje · Segundo Ciclo Nivel Primario", "level": "primaria", "orders": [4, 5, 6],
     "scale_type": "numeric", "min": 0, "max": 100, "pass_mark": 65, "competencies": COMP_3, "periods": PERIODS, "scale": SCALE_NUM,
     "official_validation": VALIDATION},
    {"key": "MINERD-SEC", "version": "2026.1", "name": "Informe de Aprendizaje · Nivel Secundario", "level": "secundaria", "orders": [],
     "scale_type": "numeric", "min": 0, "max": 100, "pass_mark": 70, "competencies": COMP_3, "periods": PERIODS, "scale": SCALE_NUM,
     "official_validation": VALIDATION},
]

SUBJECTS = [
    ("LEN", "Lengua Española", "inicial,primaria,secundaria"), ("MAT", "Matemática", "inicial,primaria,secundaria"),
    ("SOC", "Ciencias Sociales", "inicial,primaria,secundaria"), ("NAT", "Ciencias de la Naturaleza", "inicial,primaria,secundaria"),
    ("EFI", "Educación Física", "primaria,secundaria"), ("FIHR", "Formación Integral, Humana y Religiosa", "primaria,secundaria"),
    ("ART", "Educación Artística", "inicial,primaria,secundaria"), ("ING", "Lenguas Extranjeras (Inglés)", "secundaria"),
    ("FRA", "Lenguas Extranjeras (Francés)", "secundaria"),
]


def pick_template(templates: list, level: str, order: int):
    for t in templates:
        if t["level"] == level and (not t["orders"] or order in t["orders"]):
            return t
    return None
