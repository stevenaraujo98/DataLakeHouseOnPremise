"""Gold contract and calculations, independent of Streamlit and S3."""
import math
import re

BUCKET = "processed-data"
PREFIX = "gold/PowerBI/Canvas/"
FILES = ("materias_e_learning", "canvas_grado", "canvas_postgrado", "cuota_asignada")
CATEGORIES = ("Menos de 80%", "Entre 80% y 95%", "Superior a 95%")
REQUIRED = {
    "materias_e_learning": {"SIS_SOURCE_ID", "ESELEARNING", "MATERIA", "CODACAD", "TIPOMATERIA"},
    "canvas_grado": {"course_id", "sis_source_id", "course_name", "course_code", "term_name", "quota_mb", "used_mb"},
    "canvas_postgrado": {"course_id", "sis_source_id", "course_name", "course_code", "term_name", "quota_mb", "used_mb"},
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
    for table, level in [("canvas_grado", "GRADO"), ("canvas_postgrado", "POSGRADO")]:
        courses = unique_index(tables[table], "course_id", table)
        for course_id, row in courses.items():
            if numeric(course_id) is None or float(course_id) != int(float(course_id)):
                raise ValueError(f"{table}: course_id inválido.")
            meta = catalog.get(row["sis_source_id"], {})
            quota_mb = numeric(row["quota_mb"])
            assigned = quota_mb / 1000 if quota_mb is not None and quota_mb > 0 else None
            source = "Canvas quota_mb" if assigned is not None else "Sin cuota"
            # Auxiliary IDs are assumed to be grado (notebook: 42454–45768).
            # Fill missing quotas only; never join the separate Canvas instances on ID.
            fallback = numeric(quotas.get(course_id, {}).get("storage_quota_gb")) if level == "GRADO" else None
            if assigned is None and fallback is not None and fallback > 0:
                assigned, source = fallback, "cuota_asignada.storage_quota_gb"
            used_mb = numeric(row["used_mb"])
            used = used_mb / 1000 if used_mb is not None else None
            percent = used / assigned * 100 if used is not None and assigned is not None else None
            parallel = re.search(r"Paralelo\s*(\d+)", str(row["course_code"]), re.IGNORECASE)
            kind = str(meta.get("TIPOMATERIA") or "Sin información")
            kind = {"teorica": "Teórica", "practica": "Práctica", "teoricoPractica": "Teórico-práctica"}.get(kind, kind)
            result.append({
                "id": int(course_id), "nivel": level,
                "unidad": str(meta.get("CODACAD") or ("POSGRADO" if level == "POSGRADO" else "Sin unidad")),
                "materia": str(meta.get("MATERIA") or row["course_name"] or "Sin nombre"),
                "paralelo": "P" + parallel.group(1) if parallel else "Sin paralelo",
                "tipo": kind, "periodo": str(row["term_name"] or "Sin período"),
                "assigned": assigned, "used": used, "percent": percent,
                "estado": category(percent), "fuente_cuota": source,
                "elearning": str(meta.get("ESELEARNING", "")).strip().upper() == "S",
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
