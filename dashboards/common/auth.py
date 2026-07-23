import yaml
from yaml.loader import SafeLoader
import streamlit as st
import streamlit_authenticator as stauth


def login_gate(config_path: str = "config.yaml") -> tuple[str, str]:
    """Muestra el formulario de login y detiene la app si no hay sesión válida.

    Devuelve (username, role) cuando el login es exitoso. `role` viene del
    campo `role` de cada usuario en config.yaml (por defecto "cliente").
    """
    with open(config_path) as f:
        config = yaml.load(f, Loader=SafeLoader)

    authenticator = stauth.Authenticate(
        config["credentials"],
        config["cookie"]["name"],
        config["cookie"]["key"],
        config["cookie"]["expiry_days"],
    )

    authenticator.login()

    status = st.session_state.get("authentication_status")
    if status is False:
        st.error("Usuario o contraseña incorrectos")
        st.stop()
    elif status is None:
        st.warning("Ingresa tus credenciales")
        st.stop()

    username = st.session_state["username"]
    role = config["credentials"]["usernames"][username].get("role", "cliente")

    with st.sidebar:
        st.caption(f"Sesión: {st.session_state['name']} ({role})")
        authenticator.logout("Cerrar sesión")

    return username, role
