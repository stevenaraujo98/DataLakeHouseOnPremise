"""Escaped HTML views matching the two Power BI references."""
from html import escape
from data import CATEGORIES, number


def state_class(row):
    return ("low", "medium", "high")[CATEGORIES.index(row["estado"])] if row["estado"] in CATEGORIES else "unknown"


def gauge(percent):
    # A semicircle with a real 80% marker; text preserves consumption above 100%.
    value = max(0, min(percent or 0, 100))
    return (
        '<div class="gauge"><svg viewBox="0 0 240 145" role="img" aria-label="Uso global: ' + number(percent, 2, ' %') + '">'
        '<path d="M 25 115 A 90 90 0 0 1 205 115" fill="none" stroke="#f1f1f1" stroke-width="27" pathLength="100"/>'
        f'<path d="M 25 115 A 90 90 0 0 1 205 115" fill="none" stroke="#ea7038" stroke-width="27" pathLength="100" stroke-dasharray="{value} 100"/>'
        '<line x1="177" y1="73" x2="199" y2="57" stroke="#171c70" stroke-width="2"/>'
        '<text x="195" y="48" fill="#666" font-size="13">80 %</text>'
        '<text x="115" y="111" text-anchor="middle" fill="#626262" font-size="24">' + number(percent, 2, ' %') + '</text>'
        '</svg><span>Uso global de almacenamiento</span></div>'
    )


def overview_html(rows, summary, elearning=True):
    cards = '<div class="kpis">'
    for label, value, kind in [
        ("Cursos E-Learning" if elearning else "Cursos Canvas", number(summary["courses"], 0), "courses"),
        ("GB Asignados", number(summary["assigned"]), "assigned"),
        ("GB Utilizados", number(summary["used"]), "used"),
    ]:
        cards += f'<div class="kpi {kind}"><strong>{label}</strong><span>{value}</span></div>'
    cards += gauge(summary["percent"]) + '</div>'
    body = []
    for row in rows:
        cls = state_class(row)
        symbol = {"low": "●", "medium": "▲", "high": "◆", "unknown": "○"}[cls]
        cells = [
            f'<span class="status-icon {cls}" aria-hidden="true">{symbol}</span> ' + escape(row["unidad"]),
            str(row["id"]), escape(row["materia"]), escape(row["paralelo"]), escape(row["tipo"]),
            number(row["assigned"]), number(row["used"]), number(row["percent"], 2, " %") if row["percent"] is not None else "Sin dato",
            escape(row["estado"]),
        ]
        body.append('<tr title="' + escape(row["nivel"] + ' · ' + row["periodo"] + ' · Cuota: ' + row["fuente_cuota"], quote=True) + '">' + ''.join(f'<td class="{cls if i == 8 else ""}">{cell}</td>' for i, cell in enumerate(cells)) + '</tr>')
    headers = ["Unidad", "ID Curso", "Materia", "Paralelo", "Tipo materia", "Asignada", "Utilizado", "% usado", "Estado"]
    return cards + '<section class="detail-panel"><h2>Detalle de cuota asignada y utilizada (GB) por curso</h2><div class="table-scroll"><table class="course-table"><thead><tr>' + ''.join('<th scope="col">' + label + '</th>' for label in headers) + '</tr></thead><tbody>' + ''.join(body) + '</tbody></table></div></section>'


def distribution_html(rows):
    panels = []
    for category, cls, title in zip(CATEGORIES, ["low", "medium", "high"], ["Cursos con Menos de 80% de uso", "Cursos de 80% a 95% de uso", "Cursos con Más de 95% de uso"]):
        selected = sorted([r for r in rows if r["estado"] == category], key=lambda r: -r["percent"])
        max_percent = max(100, max((r["percent"] for r in selected), default=0))
        bars = []
        for row in selected:
            label = row["materia"] + ' ' + row["paralelo"]
            tooltip = label + ' · ' + row["nivel"] + ' · ID ' + str(row["id"]) + ' · ' + number(row["percent"], 2, " %")
            bars.append('<div class="bar-row" title="' + escape(tooltip, quote=True) + '"><div class="bar-label">' + escape(label) + '<small>' + escape(row["nivel"]) + ' · ' + str(row["id"]) + '</small></div><div class="bar-track"><div class="bar-fill ' + cls + '" style="width:' + str(row["percent"] / max_percent * 100) + '%"></div><b>' + number(row["percent"], 2, ' %') + '</b></div></div>')
        content = ''.join(bars) if bars else '<p class="empty-category">No hay cursos en esta categoría.</p>'
        panels.append(f'<section class="category-panel"><h2 class="{cls}">{title}</h2><div class="category-content">{content}</div><footer>{len(selected)} cursos</footer></section>')
    return '<div class="distribution">' + ''.join(panels) + '</div>'
