import yaml
from yaml.loader import SafeLoader
import streamlit as st
import streamlit_authenticator as stauth


def _entra_configured() -> bool:
    """True solo si dashboards/<proyecto>/.streamlit/secrets.toml existe y
    tiene [auth] con client_id. Si no, el login con Microsoft se oculta por
    completo y la app sigue funcionando solo con usuario/contraseña."""
    try:
        auth_cfg = st.secrets.get("auth")
    except Exception:
        return False
    return bool(auth_cfg and auth_cfg.get("client_id"))


def _entra_role(config: dict, email: str) -> str | None:
    """Busca el email en la lista blanca `entra.usernames` de config.yaml.
    None si el email no está autorizado para este proyecto."""
    entra_users = (config.get("entra") or {}).get("usernames") or {}
    entry = entra_users.get(email)
    return entry.get("role") if entry else None


def login_gate(config_path: str = "config.yaml") -> tuple[str, str]:
    """Muestra el formulario de login y detiene la app si no hay sesión válida.

    Devuelve (username, role) cuando el login es exitoso. `role` viene del
    campo `role` de cada usuario en config.yaml (por defecto "cliente").

    Si el proyecto tiene dashboards/<proyecto>/.streamlit/secrets.toml
    configurado (ver STREAMLIT_GUIDE.md), también ofrece "Iniciar sesión
    con Microsoft" -- el email autenticado debe estar en la lista blanca
    `entra.usernames` de config.yaml, igual de restringido que el login
    usuario/contraseña.
    """
    with open(config_path) as f:
        config = yaml.load(f, Loader=SafeLoader)

    entra_on = _entra_configured()

    if entra_on and st.user.is_logged_in:
        role = _entra_role(config, st.user.email)
        if role is None:
            st.error(f"Tu cuenta ({st.user.email}) no tiene acceso a este dashboard.")
            st.button("Cerrar sesión", on_click=st.logout)
            st.stop()

        with st.sidebar:
            st.caption(f"Sesión: {st.user.name} ({role}) · Microsoft")
            st.button("Cerrar sesión", on_click=st.logout)

        return st.user.email, role

    authenticator = stauth.Authenticate(
        config["credentials"],
        config["cookie"]["name"],
        config["cookie"]["key"],
        config["cookie"]["expiry_days"],
    )

    authenticator.login()

    status = st.session_state.get("authentication_status")

    if entra_on and status is not True:
        st.divider()
        if st.button("Iniciar sesión con Microsoft"):
            st.login()

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
