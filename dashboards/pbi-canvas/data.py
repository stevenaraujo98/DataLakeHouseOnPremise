"""Gold contract and calculations, independent of Streamlit and S3."""
import math

BUCKET = "processed-data"
PREFIX = "gold/PowerBI/Canvas/"
FILES = ("materias_e_learning", "canvas", "cuota_asignada")
CATEGORIES = ("Menos de 80%", "Entre 80% y 95%", "Superior a 95%")
REQUIRED = {
    "materias_e_learning": {"SIS_SOURCE_ID", "MATERIA", "CODACAD", "TIPOMATERIA"},
    "canvas": {"course_id", "sis_source_id", "course_name", "term_name", "used_gb", "PARALELO"},
    "cuota_asignada": {"id", "storage_quota_gb"},
}


def numeric(value):
    try:
        result = float(value)
        return result if math.isfinite(result) and result >= 0 else None
    except (TypeError, ValueError):
        return None


def number(value, decimals=2, suffix=""):
    if value is None:
        return "Sin dato"
    return f"{value:,.{decimals}f}".replace(",", "_").replace(".", ",").replace("_", ".") + suffix


def category(percent):
    if percent is None:
        return "Sin cuota / uso"
    return CATEGORIES[0] if percent < 80 else CATEGORIES[1] if percent <= 95 else CATEGORIES[2]


def unique_index(rows, key, name):
    result = {}
    for row in rows:
        value = row[key]
        if value is None or value == "":
            continue
        if value in result and row != result[value]:
            raise ValueError(f"{name}: registros contradictorios para {key}={value}.")
        result[value] = row
    return result


def build_courses(tables):
    for name, columns in REQUIRED.items():
        if name not in tables or not isinstance(tables[name], list):
            raise ValueError(f"Falta la tabla {name}.")
        for row in tables[name]:
            missing = columns - row.keys()
            if missing:
                raise ValueError(f"{name}: faltan columnas {', '.join(sorted(missing))}.")
    catalog = unique_index(tables["materias_e_learning"], "SIS_SOURCE_ID", "materias_e_learning")
    quotas = unique_index(tables["cuota_asignada"], "id", "cuota_asignada")
    result = []
    courses = unique_index(tables["canvas"], "course_id", "canvas")
    for course_id, row in courses.items():
        # Inner join: membership in the already filtered gold catalog is enough.
        # Null catalog keys are not indexed and cannot match null Canvas keys.
        meta = catalog.get(row["sis_source_id"])
        if meta is None:
            continue
        if numeric(course_id) is None or float(course_id) != int(float(course_id)):
            raise ValueError("canvas: course_id inválido.")
        assigned = numeric(quotas.get(course_id, {}).get("storage_quota_gb"))
        assigned = assigned if assigned is not None and assigned > 0 else None
        source = "cuota_asignada.storage_quota_gb" if assigned is not None else "Sin cuota"
        used = numeric(row["used_gb"])
        percent = used / assigned * 100 if used is not None and assigned is not None else None
        unit = str(meta.get("CODACAD") or "Sin unidad")
        level = "POSGRADO" if unit.strip().upper() == "POSGRADO" else "GRADO" if unit != "Sin unidad" else "Sin nivel"
        kind = str(meta.get("TIPOMATERIA") or "Sin información")
        kind = {"teorica": "Teórica", "practica": "Práctica", "teoricoPractica": "Teórico-práctica"}.get(kind, kind)
        result.append({
            "id": int(course_id), "nivel": level, "unidad": unit,
            "materia": str(meta.get("MATERIA") or row["course_name"] or "Sin nombre"),
            "paralelo": str(row["PARALELO"] or "Sin paralelo"),
            "tipo": kind, "periodo": str(row["term_name"] or "Sin período"),
            "assigned": assigned, "used": used, "percent": percent,
            "estado": category(percent), "fuente_cuota": source,
        })
    return result


def summarize(rows):
    complete = [r for r in rows if r["percent"] is not None]
    assigned = sum(r["assigned"] for r in rows if r["assigned"] is not None)
    used = sum(r["used"] for r in rows if r["used"] is not None)
    denominator = sum(r["assigned"] for r in complete)
    return {
        "courses": len(rows),
        "assigned": assigned if any(r["assigned"] is not None for r in rows) else None,
        "used": used if any(r["used"] is not None for r in rows) else None,
        "percent": sum(r["used"] for r in complete) / denominator * 100 if denominator else None,
    }
