"""PDF plegable del Informe de Aprendizaje: A4 horizontal, 2 caras (exterior: contraportada | portada; interior: desempeño)."""
import io
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph, Table, TableStyle

W, H = landscape(A4)
ORANGE = colors.HexColor("#E8833A")
NAVY = colors.HexColor("#0B1B33")
S = ParagraphStyle("s", fontName="Helvetica", fontSize=7, leading=8.5)
SB = ParagraphStyle("sb", parent=S, fontName="Helvetica-Bold")
HEAD = ParagraphStyle("h", parent=SB, textColor=colors.white, alignment=1)


def _p(t, st=S):
    return Paragraph(escape(str(t if t not in (None, "") else "—")), st)


def _band(c, x, y, w, text):
    c.setFillColor(ORANGE)
    c.rect(x, y, w, 13, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 8)
    c.drawCentredString(x + w / 2, y + 4, text)
    c.setFillColor(colors.black)


def _draw(c, flow, x, y_top, w):
    _, h = flow.wrap(w, H)
    flow.drawOn(c, x, y_top - h)
    return y_top - h


def _watermark(c, card):
    if card["status"] != "emitido":
        c.saveState()
        c.setFillColor(colors.Color(0.85, 0.1, 0.1, alpha=0.12))
        c.setFont("Helvetica-Bold", 48)
        c.translate(W / 2, H / 2)
        c.rotate(25)
        c.drawCentredString(0, 0, "BORRADOR · NO OFICIAL")
        c.restoreState()


def _sign_block(c, x, y, w, label, approval):
    c.line(x, y, x + w, y)
    c.setFont("Helvetica-Bold", 7)
    c.drawString(x, y - 9, label)
    c.setFont("Helvetica", 6.5)
    if approval:
        c.drawString(x, y - 18, f"Aprobado en sistema por {approval['by_name']} · {approval['at'][:16].replace('T', ' ')} UTC")
        c.drawString(x, y - 26, "Firma manuscrita requerida. La aprobación en sistema no es firma digital.")
    else:
        c.setFillColor(colors.red)
        c.drawString(x, y - 18, "Pendiente de firma / aprobación")
        c.setFillColor(colors.black)


def _exterior(c, card):
    cov, t = card["cover"], card["template"]
    half = W / 2
    m = 14 * mm
    # Panel izquierdo (contraportada)
    _band(c, m, H - m - 13, half - 2 * m, "FIRMA DEL PADRE, MADRE O TUTOR")
    y = H - m - 30
    c.setFont("Helvetica", 8)
    c.drawString(m, y, "Períodos de reporte de calificaciones")
    for p in t["periods"]:
        y -= 22
        c.drawString(m, y, p["months"])
        c.line(m + 70, y - 2, half - m, y - 2)
    y -= 30
    _band(c, m, y, half - 2 * m, "AVANCE DE LOS APRENDIZAJES Y APOYOS NECESARIOS")
    support = " ".join(f"{k}: {v}" for k, v in card["support"].items() if v) or "Pendiente de registro por el docente titular."
    _draw(c, _p(support), m, y - 6, half - 2 * m)
    # Panel derecho (portada)
    x0 = half + m
    pw = half - 2 * m
    c.setFont("Helvetica-Bold", 9)
    c.drawCentredString(x0 + pw / 2, H - m - 10, "REPÚBLICA DOMINICANA · MINISTERIO DE EDUCACIÓN (MINERD)")
    c.setFont("Helvetica", 7.5)
    c.drawCentredString(x0 + pw / 2, H - m - 22, f"Regional: {cov['regional'] or '—'}   ·   Distrito: {cov['district'] or '—'}")
    c.setFillColor(ORANGE)
    c.setFont("Helvetica-Bold", 20)
    c.drawCentredString(x0 + pw / 2, H - m - 70, "INFORME DE APRENDIZAJE")
    c.setFillColor(NAVY)
    c.setFont("Helvetica-Bold", 15)
    c.drawCentredString(x0 + pw / 2, H - m - 100, cov["grade"].upper())
    c.setFont("Helvetica-Bold", 11)
    c.drawCentredString(x0 + pw / 2, H - m - 116, f"NIVEL {cov['level'].upper()}")
    c.setFillColor(colors.black)
    c.setFont("Helvetica", 8)
    c.drawCentredString(x0 + pw / 2, H - m - 132, f"Año escolar: {cov['year']}")
    rows = [("Sección", cov["section"]), ("Número de orden", cov["order_number"]), ("Nombre(s)", cov["first_name"]), ("Apellido(s)", cov["last_name"]),
            ("ID estudiante", cov["student_code"]), ("Docente titular", cov["teacher"] or "Pendiente de asignación"),
            ("Centro educativo", cov["institution"]), ("Sede", cov["campus"]), ("Director/a", cov["director"] or "Pendiente")]
    y = H - m - 160
    for k, v in rows:
        c.setFont("Helvetica-Bold", 8)
        c.drawString(x0 + 10, y, f"{k}:")
        c.setFont("Helvetica", 8)
        c.drawString(x0 + 95, y, str(v))
        c.line(x0 + 92, y - 2, x0 + pw - 10, y - 2)
        y -= 18
    c.setFont("Helvetica-Oblique", 6)
    c.drawString(x0, m, f"Plantilla {t['key']} v{t['version']} · {t['official_validation']} · Versión contenido {card['content_hash']}")
    c.setDash(2, 3)
    c.line(half, m / 2, half, H - m / 2)
    c.setDash()
    _watermark(c, card)


def _interior(c, card):
    t = card["template"]
    m = 10 * mm
    comps, periods = t["competencies"], [p["key"] for p in t["periods"]]
    _band(c, m, H - m - 13, W - 2 * m, "DESEMPEÑO INDIVIDUAL DEL/LA ESTUDIANTE")
    head1 = [_p("Competencias fundamentales", SB)] + sum([[_p(cp["name"], SB)] + [""] * (len(periods) - 1) for cp in comps], []) + \
            [_p("Calificación final por competencia", SB)] + [""] * (len(comps) - 1) + [_p("Final área", SB), _p("Recup.", SB)]
    head2 = [_p("Áreas curriculares / Períodos", SB)] + sum([[_p(p, SB) for p in periods] for _ in comps], []) + \
            [_p(cp["key"], SB) for cp in comps] + ["", ""]
    body = []
    for r in card["grid"]:
        cells = [_p(r["subject"])]
        for cp in comps:
            cells += [_p(r["periods"][cp["key"]].get(p, "")) for p in periods]
        cells += [_p(r["finals"].get(cp["key"], "")) for cp in comps] + [_p(r["final"]), _p(r["recovery"])]
        body.append(cells)
    n = len(head1)
    first = 42 * mm
    cw = [first] + [(W - 2 * m - first) / (n - 1)] * (n - 1)
    tbl = Table([head1, head2] + body, colWidths=cw, repeatRows=2)
    style = [("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#E0A070")), ("BACKGROUND", (0, 0), (-1, 1), colors.HexColor("#FBE3CF")),
             ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("ALIGN", (1, 2), (-1, -1), "CENTER")]
    col = 1
    for _ in comps:
        style.append(("SPAN", (col, 0), (col + len(periods) - 1, 0)))
        col += len(periods)
    style.append(("SPAN", (col, 0), (col + len(comps) - 1, 0)))
    tbl.setStyle(TableStyle(style))
    y = _draw(c, tbl, m, H - m - 16, W - 2 * m) - 6
    obs = Table([[_p("Observaciones", SB), ""]] + [[_p(p, SB), _p(card["observations"].get(p) or "Pendiente")] for p in periods],
                colWidths=[14 * mm, W - 2 * m - 14 * mm])
    obs.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#E0A070")), ("SPAN", (0, 0), (1, 0)),
                             ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#FBE3CF"))]))
    y = _draw(c, obs, m, y, W - 2 * m) - 6
    att = [[_p("Períodos", SB), _p("Asistencia", SB), _p("Ausencia", SB), _p("% Asist.", SB)]] + \
          [[_p(a["period"]), _p(a["present"]), _p(a["absent"]), _p(a["pct"])] for a in card["attendance"]] + \
          [[_p("Anual", SB), _p(card["attendance_total"]["present"]), _p(card["attendance_total"]["absent"]), _p(card["attendance_total"]["pct"])]]
    at = Table(att, colWidths=[18 * mm, 20 * mm, 20 * mm, 18 * mm])
    at.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#E0A070")), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#FBE3CF"))]))
    legend = [[_p("Leyenda", SB)]] + [[_p(f"({p['key']}) Período {i + 1} · {p['months']}")] for i, p in enumerate(t["periods"])] + \
             [[_p(f"({cp['key']}) Competencia {i + 1}")] for i, cp in enumerate(comps)]
    lg = Table(legend, colWidths=[52 * mm])
    lg.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.3, colors.HexColor("#E0A070"))]))
    scale_rows = [[_p("Escala", SB), _p("Descripción", SB)]] + [[_p(f"{s['min']}-{s['max']} {s['label']}"), _p(s["description"])] for s in t["scale"]] \
        if t["scale"] else [[_p("Escala", SB), _p("Cualitativa: " + ", ".join(f"{v['key']} = {v['label']}" for v in t.get("values", [])))]]
    sc = Table(scale_rows, colWidths=[24 * mm, W - 2 * m - 76 * mm - 52 * mm - 24 * mm - 12])
    sc.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#E0A070")), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#FBE3CF"))]))
    _draw(c, at, m, y, 76 * mm)
    _draw(c, lg, m + 76 * mm + 6, y, 52 * mm)
    _draw(c, sc, m + 128 * mm + 12, y, W - 2 * m)
    _sign_block(c, m, 18 * mm, 90 * mm, f"Docente titular: {card['cover']['teacher'] or '—'}", card["approvals"].get("docente"))
    _sign_block(c, W / 2 + 10 * mm, 18 * mm, 90 * mm, f"Director/a: {card['cover']['director'] or '—'}", card["approvals"].get("direccion"))
    _watermark(c, card)


def build_report_cards_pdf(cards: list) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(W, H))
    c.setTitle("Informe de Aprendizaje")
    for card in cards:
        _exterior(c, card)
        c.showPage()
        _interior(c, card)
        c.showPage()
    c.save()
    return buf.getvalue()
