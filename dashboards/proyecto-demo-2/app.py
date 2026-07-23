import streamlit as st
from common.auth import login_gate

st.set_page_config(page_title="Proyecto Demo 2", layout="wide")

username, role = login_gate()

st.title("Proyecto Demo 2")
st.success(f"Bienvenido, {username}")

if role == "admin":
    st.markdown("### Panel de administración")
    st.info("Esta sección solo la ve el rol 'admin'.")

st.markdown("### Contenido del dashboard")
st.write(
    "Este es un segundo proyecto de ejemplo, aislado del Proyecto Demo 1: "
    "otra ruta (`/proyecto-demo-2`), otro `config.yaml`, otros usuarios y "
    "otra cookie de sesión. Usuarios de prueba: `cliente2` / `Demo5678!` y "
    "`admin2` / `Admin5678!`."
)
