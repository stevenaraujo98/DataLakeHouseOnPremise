import streamlit as st
import os

st.set_page_config(page_title="DataLakeHouse Dashboard", layout="wide")

st.title("🏠 DataLakeHouse On-Premise")
st.success("✅ Stack funcionando correctamente")

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

st.markdown("---")
st.caption("Universidad - DataScience Stack v1.0")