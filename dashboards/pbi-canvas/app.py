"""Canvas storage dashboard. Run with Streamlit from this directory."""
import io
import os
from pathlib import Path
from zoneinfo import ZoneInfo

import boto3
import polars as pl
import streamlit as st
from botocore.exceptions import BotoCoreError, ClientError
from common.auth import login_gate
from data import FILES, PREFIX, BUCKET, build_courses, summarize
from views import overview_html, distribution_html


@st.cache_resource
def s3_client():
    return boto3.client(
        "s3", endpoint_url=os.environ["MINIO_ENDPOINT"],
        aws_access_key_id=os.environ["MINIO_ACCESS_KEY"],
        aws_secret_access_key=os.environ["MINIO_SECRET_KEY"],
    )


@st.cache_data(ttl=300, max_entries=2)
def load_data():
    """Read the unified Canvas gold schema and its two related tables."""
    tables, modified = {}, []
    for name in FILES:
        response = s3_client().get_object(Bucket=BUCKET, Key=PREFIX + name + ".parquet")
        try:
            tables[name] = pl.read_parquet(io.BytesIO(response["Body"].read())).to_dicts()
        finally:
            response["Body"].close()
        modified.append(response["LastModified"])
    return build_courses(tables), min(modified), max(modified)


def select_filter(label, rows, field):
    selected = st.sidebar.multiselect(label, sorted({r[field] for r in rows}))
    return [r for r in rows if r[field] in selected] if selected else rows


def main():
    st.set_page_config(page_title="Canvas · Almacenamiento", page_icon="📊", layout="wide")
    st.markdown("<style>" + Path(__file__).with_name("style.css").read_text(encoding="utf-8") + "</style>", unsafe_allow_html=True)
    login_gate()
    st.sidebar.title("Canvas")
    st.sidebar.caption("Capacidad y consumo de almacenamiento")
    if st.sidebar.button("Actualizar datos", use_container_width=True):
        load_data.clear()
    try:
        rows, oldest, newest = load_data()
    except ClientError as error:
        missing = str(error.response.get("Error", {}).get("Code")) in {"NoSuchKey", "404", "NotFound"}
        st.warning("Faltan archivos gold de Canvas. Publica los tres Parquet del notebook 4_dashboard_canvas.ipynb." if missing else "No se pudieron leer los datos. Revisa los permisos de MinIO.")
        st.stop()
    except (BotoCoreError, OSError):
        st.error("No se pudo conectar con MinIO. Revisa la conexión del servicio.")
        st.stop()
    except KeyError:
        st.error("Falta la configuración de conexión a MinIO.")
        st.stop()
    except (ValueError, pl.exceptions.PolarsError) as error:
        st.error("Los archivos gold no tienen el formato esperado.")
        st.caption(str(error))
        st.stop()
    zone = ZoneInfo("America/Guayaquil")
    st.sidebar.caption("Archivos actualizados entre " + oldest.astimezone(zone).strftime("%d/%m/%Y %H:%M") + " y " + newest.astimezone(zone).strftime("%d/%m/%Y %H:%M") + " (Guayaquil)")
    st.sidebar.caption("Cursos E-Learning con coincidencia en el catálogo gold de materias.")
    for label, field in [("Nivel", "nivel"), ("Unidad", "unidad"), ("Período / cohorte", "periodo"), ("Tipo de materia", "tipo")]:
        rows = select_filter(label, rows, field)
    search = st.sidebar.text_input("Buscar materia o ID de curso").strip().casefold()
    if search:
        rows = [r for r in rows if search in r["materia"].casefold() or search in str(r["id"])]
    st.sidebar.caption("Sin selección se incluyen todas las opciones. Los filtros se aplican a ambas pestañas.")
    if not rows:
        st.info("No hay cursos para los filtros seleccionados.")
        return
    summary = summarize(rows)
    capacity, distribution = st.tabs(["Capacidad y uso", "Distribución por consumo"])
    with capacity:
        st.markdown('<h1>Capacidad asignada y uso de almacenamiento en cursos E-Learning</h1>', unsafe_allow_html=True)
        sort = st.selectbox("Orden del detalle", ["Mayor consumo (%)", "Materia", "ID curso"])
        ordered = sorted(rows, key=lambda r: (r["percent"] is None, -(r["percent"] or 0), r["materia"])) if sort == "Mayor consumo (%)" else sorted(rows, key=lambda r: r["materia"] if sort == "Materia" else r["id"])
        st.markdown(overview_html(ordered, summary), unsafe_allow_html=True)
        st.caption("Uso y cuota se leen en GB desde gold. Uso global = utilizado / asignado, calculado sobre cursos con cuota y uso válidos. Los valores ausentes no se convierten en cero.")
        missing = sum(r["percent"] is None for r in rows)
        if missing:
            st.info(f"{missing} cursos sin cuota positiva o sin uso válido: aparecen sin porcentaje y quedan fuera del indicador global y de las tres categorías.")
        export = pl.DataFrame(ordered)
        st.download_button("Descargar detalle (CSV)", export.write_csv(), file_name="canvas_almacenamiento.csv", mime="text/csv")
    with distribution:
        st.markdown('<h1>Distribución por categoría de consumo</h1>', unsafe_allow_html=True)
        st.markdown(distribution_html(rows), unsafe_allow_html=True)
        st.caption("Categorías excluyentes: menos de 80 %, de 80 % a 95 % (incluidos), más de 95 %. Cada barra identifica el curso, su nivel y su ID.")


if __name__ == "__main__":
    main()
