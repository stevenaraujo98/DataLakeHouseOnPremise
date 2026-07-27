import json
import os

import boto3
import plotly.express as px
import polars as pl
import streamlit as st
from botocore.exceptions import ClientError
from common.auth import login_gate

st.set_page_config(page_title="Chatbot TH - Analítica", layout="wide")

username, role = login_gate()

BUCKET = "processed-data"
METRICS_KEY = "gold/th/chatbot/metrics.json"
MENSAJES_KEY = "gold/th/chatbot/mensajes.parquet"


@st.cache_resource
def get_s3_client():
    return boto3.client(
        "s3",
        endpoint_url=os.environ["MINIO_ENDPOINT"],
        aws_access_key_id=os.environ["MINIO_ACCESS_KEY"],
        aws_secret_access_key=os.environ["MINIO_SECRET_KEY"],
    )


@st.cache_data(ttl=300)
def cargar_metricas():
    obj = get_s3_client().get_object(Bucket=BUCKET, Key=METRICS_KEY)
    return json.loads(obj["Body"].read())


@st.cache_data(ttl=300)
def cargar_mensajes():
    obj = get_s3_client().get_object(Bucket=BUCKET, Key=MENSAJES_KEY)
    return pl.read_parquet(obj["Body"].read())


st.title("Chatbot TH · Panel de analítica")
st.caption(f"Sesión: {username} ({role})")

try:
    metricas = cargar_metricas()
except ClientError:
    st.warning(
        "Todavía no se han generado métricas en "
        f"`s3://{BUCKET}/{METRICS_KEY}`. Ejecuta `notebooks/2_analysis.ipynb` "
        "para generarlas."
    )
    st.stop()

col1, col2, col3, col4 = st.columns(4)
col1.metric("Mensajes totales", metricas["total_mensajes"])
col2.metric("Usuarios únicos", metricas["total_usuarios"])
col3.metric("Sesiones", metricas["total_sesiones"])
col4.metric("Mensajes con tool", metricas["usa_tool_counts"].get("True", 0))

st.divider()

col_izq, col_der = st.columns(2)

with col_izq:
    st.subheader("Distribución de sentimiento")
    sentiment_df = pl.DataFrame(
        {
            "sentimiento": list(metricas["sentiment_counts"].keys()),
            "mensajes": list(metricas["sentiment_counts"].values()),
        }
    )
    st.plotly_chart(
        px.bar(sentiment_df, x="sentimiento", y="mensajes"),
        use_container_width=True,
    )

with col_der:
    st.subheader("Uso de herramientas (tools)")
    if metricas["tools_counts"]:
        tools_df = pl.DataFrame(
            {
                "tool": list(metricas["tools_counts"].keys()),
                "usos": list(metricas["tools_counts"].values()),
            }
        ).sort("usos", descending=True)
        st.plotly_chart(
            px.bar(tools_df, x="usos", y="tool", orientation="h"),
            use_container_width=True,
        )
    else:
        st.info("Aún no hay datos de uso de tools.")

st.subheader("Mensajes por día")
serie_df = pl.DataFrame(
    {
        "fecha": list(metricas["mensajes_por_dia"].keys()),
        "mensajes": list(metricas["mensajes_por_dia"].values()),
    }
).sort("fecha")
st.plotly_chart(
    px.line(serie_df, x="fecha", y="mensajes", markers=True),
    use_container_width=True,
)

st.subheader("Usuarios más activos")
top_df = pl.DataFrame(
    {
        "usuario_cedula": list(metricas["top_usuarios"].keys()),
        "mensajes": list(metricas["top_usuarios"].values()),
    }
)
st.dataframe(top_df, use_container_width=True, hide_index=True)

if role == "admin":
    st.divider()
    st.markdown("### Detalle de conversaciones (solo admin)")
    try:
        st.dataframe(cargar_mensajes(), use_container_width=True, hide_index=True)
    except ClientError:
        st.info(
            "Todavía no se ha generado el detalle de mensajes en "
            f"`s3://{BUCKET}/{MENSAJES_KEY}`."
        )

st.caption(f"Datos generados: {metricas['generado_en']}")
