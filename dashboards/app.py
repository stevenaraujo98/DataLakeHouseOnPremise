import streamlit as st
import os
import mlflow
import pandas as pd

st.set_page_config(page_title="DataLakeHouse Dashboard", layout="wide")

st.title("DataLakeHouse On-Premise")
st.success("Stack funcionando correctamente")

# --- Links de servicios ---
st.markdown("### Servicios disponibles")
col1, col2, col3 = st.columns(3)

server_ip = os.getenv("SERVER_IP", "localhost")

with col1:
    st.info(f"**MinIO Console**\nhttp://{server_ip}:9001")
    st.info(f"**MLflow**\nhttp://{server_ip}:5000")

with col2:
    st.info(f"**JupyterHub**\nhttp://{server_ip}:8000")
    st.info(f"**Prefect**\nhttp://{server_ip}:4200")

with col3:
    st.info(f"**Streamlit**\nhttp://{server_ip}:8501")
    st.info(f"**PostgreSQL**\n{server_ip}:5432")

# --- Experimentos MLflow ---
st.markdown("---")
st.markdown("### Experimentos MLflow")

mlflow_uri = os.getenv("MLFLOW_TRACKING_URI", "http://mlflow:5000")
mlflow.set_tracking_uri(mlflow_uri)

try:
    experiments = mlflow.search_experiments()
    if not experiments:
        st.info("No hay experimentos registrados aún.")
    else:
        for exp in experiments:
            with st.expander(f"Experimento: {exp.name}  (ID: {exp.experiment_id})"):
                runs = mlflow.search_runs(experiment_ids=[exp.experiment_id])
                if runs.empty:
                    st.write("Sin runs registrados.")
                else:
                    # Mostrar solo columnas relevantes si existen
                    cols = [c for c in runs.columns
                            if c.startswith("params.") or c.startswith("metrics.")
                            or c in ("run_id", "status", "start_time")]
                    st.dataframe(runs[cols], use_container_width=True)
except Exception as e:
    st.error(f"No se pudo conectar a MLflow ({mlflow_uri}): {e}")

st.markdown("---")
st.caption("Universidad - DataScience Stack v1.0")