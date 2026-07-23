import streamlit as st
from common.auth import login_gate

st.set_page_config(page_title="Proyecto Demo 1", layout="wide")

username, role = login_gate()

st.title("Proyecto Demo 1")
st.success(f"Bienvenido, {username}")

if role == "admin":
    st.markdown("### Panel de administración")
    st.info("Esta sección solo la ve el rol 'admin'.")

st.markdown("### Contenido del dashboard")
st.write(
    "Este es un proyecto de ejemplo funcional para probar el patrón de "
    "enrutamiento por Traefik (`/proyecto-demo-1`) y el login por proyecto. "
    "Usuarios de prueba: `cliente1` / `Demo1234!` y `admin1` / `Admin1234!`."
)
