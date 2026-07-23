import streamlit as st
from common.auth import login_gate

st.set_page_config(page_title="Nombre del proyecto", layout="wide")

username, role = login_gate()

st.title("Nombre del proyecto")
st.success(f"Bienvenido, {username}")

if role == "admin":
    st.markdown("### Panel de administración")
    st.info("Esta sección solo la ve el rol 'admin'. Bórrala o reemplázala según el proyecto.")

st.markdown("### Contenido del dashboard")
st.write("Reemplaza este contenido con las visualizaciones del proyecto (MinIO, MLflow, etc.).")
