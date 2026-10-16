import io
import json
import math
import os
from datetime import date, datetime
from textwrap import shorten
from zoneinfo import ZoneInfo

import boto3
import plotly.express as px
import polars as pl
import streamlit as st
from botocore.exceptions import BotoCoreError, ClientError
from common.auth import login_gate

BUCKET = "processed-data"
METRICS_KEY = "gold/th/chatbot/metrics.json"
MENSAJES_KEY = "gold/th/chatbot/mensajes.parquet"
INCIDENCIAS = {
    "error_model": "Error del modelo",
    "Limitante": "Limitante",
    "Language_analysis_lizura": "Lenguaje inapropiado",
}


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
    datos = json.loads(obj["Body"].read())
    if not isinstance(datos, dict) or "total_usuarios" not in datos:
        raise ValueError("El archivo de métricas no contiene los KPIs esperados.")
    return datos


@st.cache_data(ttl=300, max_entries=4)
def cargar_mensajes(generado_en):
    # La generación forma parte de la clave de caché: un JSON nuevo renueva el detalle.
    obj = get_s3_client().get_object(Bucket=BUCKET, Key=MENSAJES_KEY)
    return pl.read_parquet(io.BytesIO(obj["Body"].read()))


def es_ausente(error):
    return str(error.response.get("Error", {}).get("Code")) in {"404", "NoSuchKey", "NotFound"}


def tabla(registros):
    return pl.DataFrame(registros, infer_schema_length=None, strict=False) if registros else pl.DataFrame()


def numero(valor, decimales=0, sufijo=""):
    if valor is None or not math.isfinite(float(valor)):
        return "Sin dato"
    texto = f"{float(valor):,.{decimales}f}".replace(",", "_").replace(".", ",").replace("_", ".")
    return texto + sufijo


def segundos(ms):
    return numero(ms / 1000 if ms is not None else None, 2, " s")


def fecha_generacion(valor, zona):
    if not valor:
        return "Sin fecha de actualización"
    try:
        instante = datetime.fromisoformat(valor.replace("Z", "+00:00"))
        return instante.astimezone(ZoneInfo(zona)).strftime("%d/%m/%Y %H:%M %Z")
    except (ValueError, KeyError):
        return str(valor)


def actividad_historica(metricas):
    registros = metricas.get("actividad_diaria", [])
    if registros:
        return tabla(registros).sort("fecha")
    # Compatibilidad mientras se publica el JSON del nuevo notebook.
    return tabla([
        {"fecha": fecha, "interacciones": cantidad}
        for fecha, cantidad in sorted(metricas.get("mensajes_por_dia", {}).items())
    ])


def filtrar_fechas(datos, periodo):
    if datos.is_empty() or not periodo or "fecha" not in datos.columns:
        return datos
    return datos.filter(pl.col("fecha").is_between(
        pl.lit(periodo[0].isoformat()), pl.lit(periodo[1].isoformat()),
    ))


def barra(datos, etiqueta, valor, titulo, top_n=20, ordenar=True, hover=()):
    st.subheader(titulo)
    if datos.is_empty() or not {etiqueta, valor}.issubset(datos.columns):
        st.info("No hay datos para esta visualización.")
        return
    datos = datos.filter(pl.col(valor).is_not_null())
    if ordenar:
        datos = datos.sort(valor, descending=True)
    datos = datos.head(top_n)
    if datos.is_empty():
        st.info("No hay datos para esta visualización.")
        return
    # Solo las columnas mostradas llegan al gráfico; los rankings de sesión
    # también contienen el primer mensaje, reservado al detalle de admin.
    columnas = list(dict.fromkeys([etiqueta, valor, *hover]))
    datos = datos.select([c for c in columnas if c in datos.columns])
    fig = px.bar(
        datos.to_dict(as_series=False), x=valor, y=etiqueta, orientation="h",
        hover_data=[c for c in hover if c in datos.columns],
    )
    etiquetas = datos[etiqueta].cast(pl.String).to_list()
    fig.update_yaxes(
        type="category", categoryorder="array", categoryarray=list(reversed(etiquetas)),
        tickmode="array", tickvals=etiquetas,
        ticktext=[shorten(x, width=65, placeholder="…") for x in etiquetas], title=None,
    )
    fig.update_layout(height=max(320, 30 * datos.height), margin=dict(t=15, b=35), xaxis_title=None)
    st.plotly_chart(fig, width="stretch", key=f"barra_{titulo}")


def linea_diaria(datos, columnas, titulo, etiquetas=None):
    st.subheader(titulo)
    columnas = [c for c in columnas if c in datos.columns]
    if datos.is_empty() or not columnas:
        st.info("No hay datos en el rango de fechas seleccionado.")
        return
    nombres = {
        c: {"latencia_media_s": "Media", "latencia_p50_s": "Mediana (P50)",
            "latencia_p95_s": "P95", "tasa_incidencias_pct": "Con incidencia"}.get(c, c.capitalize())
        for c in columnas
    }
    unidad = "Segundos" if any(c.endswith("_s") for c in columnas) else "Cantidad"
    if any(c.endswith("_pct") for c in columnas):
        unidad = "Porcentaje (%)"
    fig = px.line(
        datos.select(["fecha", *columnas]).rename(nombres).to_dict(as_series=False),
        x="fecha", y=list(nombres.values()), markers=True,
        labels=etiquetas or {"variable": "Serie", "value": unidad},
    )
    fig.update_layout(legend_title_text=None, xaxis_title="Fecha", margin=dict(t=15))
    st.plotly_chart(fig, width="stretch", key=f"linea_{titulo}")


def vista_resumen(metricas, actividad, top_n):
    cobertura, pendientes, tools, errores = st.columns(4)
    cobertura.metric("Cobertura de respuesta", numero(metricas.get("tasa_respuesta_pct"), 2, " %"))
    pendientes.metric("Interacciones sin respuesta", numero(metricas.get("total_sin_respuesta")))
    tools.metric("Interacciones con herramientas", numero(metricas.get("usa_tool_counts", {}).get("True", 0)))
    errores.metric("Interacciones con incidencia", numero(metricas.get("total_errores")))
    st.caption("Totales del histórico completo. Una interacción es un mensaje humano con su respuesta asociada, si existe.")

    opciones = [c for c in ("interacciones", "respuestas", "usuarios", "sesiones") if c in actividad.columns]
    elegidas = st.multiselect(
        "Series de actividad", opciones,
        default=[c for c in ("interacciones", "respuestas", "usuarios") if c in opciones],
        format_func=lambda x: x.capitalize(), key="series_actividad",
    )
    linea_diaria(actividad, elegidas, "Actividad diaria")
    st.caption("Usuarios e interacciones: día del mensaje humano. Respuestas: día de la respuesta. Zona horaria indicada en la barra lateral.")

    izquierda, derecha = st.columns(2)
    with izquierda:
        sentimientos = tabla([
            {"sentimiento": k, "interacciones": v} for k, v in metricas.get("sentiment_counts", {}).items()
        ])
        barra(sentimientos, "sentimiento", "interacciones", "Sentimiento de los usuarios")
    with derecha:
        usuarios = tabla(metricas.get("top_usuarios_detalle", []))
        if usuarios.is_empty():
            usuarios = tabla([
                {"usuario_cedula": str(k), "interacciones": v} for k, v in metricas.get("top_usuarios", {}).items()
            ])
        barra(usuarios, "usuario_cedula", "interacciones", "Usuarios más activos · histórico", top_n)
    with st.expander("Ver actividad diaria y ranking de usuarios"):
        st.dataframe(actividad, width="stretch", hide_index=True)
        st.dataframe(usuarios.head(top_n), width="stretch", hide_index=True)


def vista_conversaciones(metricas, top_n):
    st.caption("Rankings del histórico completo. Las aperturas son el primer mensaje observado por sesión e incluyen saludos.")
    inicios = metricas.get("inicios_sesion", {})
    a, b = st.columns(2)
    a.metric("Sesiones con apertura observable", numero(inicios.get("sesiones_con_inicio_observable")))
    b.metric("Mensajes para análisis temático", numero(metricas.get("mensajes_corpus_tematico")))
    izquierda, derecha = st.columns(2)
    with izquierda:
        modos = {
            "Mensajes completos": ("mensajes_frecuentes", "mensaje", "sesiones"),
            "Palabras": ("palabras_frecuentes", "termino", "frecuencia"),
            "Frases cortas": ("frases_frecuentes", "termino", "frecuencia"),
        }
        modo = st.selectbox("Aperturas de sesión", list(modos), key="modo_apertura")
        clave, etiqueta, valor = modos[modo]
        aperturas = tabla(inicios.get(clave, []))
        barra(aperturas, etiqueta, valor, "Cómo empiezan las sesiones", top_n)
        with st.expander("Ver frecuencias de apertura"):
            st.dataframe(aperturas.head(top_n), width="stretch", hide_index=True)
    with derecha:
        modo = st.selectbox("Lenguaje de los usuarios", ["Palabras", "Frases cortas"], key="modo_temas")
        temas = tabla(metricas.get("palabras_clave" if modo == "Palabras" else "frases_clave", []))
        criterio = st.selectbox(
            "Ordenar términos por", ["frecuencia", "mensajes", "usuarios", "sesiones"],
            format_func=lambda x: x.capitalize(), key="criterio_temas",
        )
        barra(temas, "termino", criterio, "Palabras y frases más usadas", top_n)
        with st.expander("Ver frecuencias de palabras y frases"):
            if not temas.is_empty():
                temas = temas.sort(criterio, descending=True)
            st.dataframe(temas.head(top_n), width="stretch", hide_index=True)
    st.caption("Frecuencia cuenta apariciones; mensajes, usuarios y sesiones se cuentan una vez por término. El análisis temático excluye saludos, confirmaciones y palabras vacías; unifica mayúsculas y tildes.")


def vista_herramientas(metricas, top_n):
    herramientas = tabla(metricas.get("herramientas", []))
    a, b, c = st.columns(3)
    a.metric("Herramientas distintas", numero(herramientas.height))
    b.metric("Llamadas registradas", numero(sum(metricas.get("tools_counts", {}).values())))
    c.metric("Interacciones con herramientas", numero(metricas.get("usa_tool_counts", {}).get("True", 0)))
    st.caption("Histórico completo. Una lista con dos llamadas a la misma herramienta cuenta dos llamadas y una interacción.")
    criterio = st.selectbox(
        "Comparar herramientas por", ["llamadas", "interacciones", "usuarios", "sesiones"],
        format_func=lambda x: x.capitalize(), key="criterio_tools",
    )
    barra(herramientas, "tool", criterio, "Uso de herramientas", top_n)
    if not herramientas.is_empty():
        tiempos = herramientas.with_columns((pl.col("latencia_p95_ms") / 1000).alias("p95_s"))
        barra(tiempos, "tool", "p95_s", "P95 de respuesta asociado a cada herramienta (s)", top_n)
        st.caption("Estos tiempos corresponden a la respuesta completa, no al tiempo de ejecución individual de la herramienta.")
        st.dataframe(herramientas, width="stretch", hide_index=True)
    st.caption("Error del modelo, Limitante y Lenguaje inapropiado se consultan en Incidencias.")


def vista_rendimiento(metricas, actividad, top_n):
    latencias = metricas.get("latencias", {})
    for columna, (etiqueta, clave) in zip(st.columns(4), [
        ("Tiempo medio", "media_ms"), ("Mediana · P50", "p50_ms"),
        ("P95", "p95_ms"), ("Máximo", "max_ms"),
    ]):
        columna.metric(etiqueta, segundos(latencias.get(clave)))
    st.caption(
        f"Histórico completo · {numero(latencias.get('respuestas_con_latencia'))} respuestas con latencia válida. "
        "P95: el 95 % de las respuestas tarda ese tiempo o menos. Los tiempos ausentes no se convierten en cero."
    )
    distribucion = tabla(metricas.get("distribucion_latencias", []))
    barra(distribucion, "rango", "respuestas", "Distribución de tiempos de respuesta", ordenar=False)

    columnas_ms = [c for c in ("latencia_media_ms", "latencia_p50_ms", "latencia_p95_ms") if c in actividad.columns]
    tiempos = actividad.with_columns([(pl.col(c) / 1000).alias(c.replace("_ms", "_s")) for c in columnas_ms])
    linea_diaria(
        tiempos, [c.replace("_ms", "_s") for c in columnas_ms],
        "Tiempos de respuesta por día de interacción (s)",
    )
    st.divider()
    modos = {
        "Sesión más lenta por usuario": ("sesion_mas_lenta_por_usuario", "usuario_cedula", "tiempo_modelo_total_s"),
        "Sesiones por tiempo acumulado del modelo": ("top_sesiones_tiempo_modelo", "session_id", "tiempo_modelo_total_s"),
        "Sesiones por duración de reloj": ("top_sesiones_duracion", "session_id", "duracion_min"),
    }
    modo = st.selectbox("Ranking de sesiones · histórico", list(modos), key="ranking_sesiones")
    clave, etiqueta, valor = modos[modo]
    sesiones = tabla(metricas.get(clave, []))
    barra(
        sesiones, etiqueta, valor,
        "Duración de sesión (min)" if valor == "duracion_min" else "Tiempo acumulado del modelo por sesión (s)",
        top_n, hover=("usuario_cedula", "session_id", "interacciones", "latencia_max_ms", "duracion_min"),
    )
    st.caption("Tiempo acumulado del modelo: suma de latencias válidas. Duración de reloj: del primer mensaje a la última respuesta o mensaje; incluye pausas del usuario y puede abarcar varios días.")
    with st.expander("Ver sesiones y respuestas más lentas"):
        campos = ["usuario_cedula", "session_id", "interacciones", "respuestas", "tiempo_modelo_total_s", "latencia_max_ms", "duracion_min"]
        st.dataframe(sesiones.select([c for c in campos if c in sesiones.columns]).head(top_n), width="stretch", hide_index=True)
        st.dataframe(tabla(metricas.get("respuestas_mas_lentas", [])).head(top_n), width="stretch", hide_index=True)


def vista_incidencias(metricas, periodo):
    conteos = metricas.get("incidencias_counts", {})
    for columna, (tipo, etiqueta) in zip(st.columns(3), INCIDENCIAS.items()):
        columna.metric(etiqueta, numero(conteos.get(tipo, 0)))
    st.caption(
        f"Histórico completo · {numero(metricas.get('total_errores'))} interacciones afectadas "
        f"({numero(metricas.get('tasa_incidencias_pct'), 2, ' %')}). "
        "Una interacción puede tener varios tipos de incidencia; el total de afectadas la cuenta una vez."
    )
    resumen = tabla([{"tipo": etiqueta, "interacciones": conteos.get(tipo, 0)} for tipo, etiqueta in INCIDENCIAS.items()])
    barra(resumen, "tipo", "interacciones", "Incidencias por tipo · histórico")
    diarias = filtrar_fechas(tabla(metricas.get("incidencias_por_dia", [])), periodo)
    if not diarias.is_empty():
        st.subheader("Incidencias por día y tipo")
        columnas = [c for c in INCIDENCIAS if c in diarias.columns]
        datos = diarias.select(["fecha", *columnas]).rename({c: INCIDENCIAS[c] for c in columnas})
        fig = px.bar(datos.to_dict(as_series=False), x="fecha", y=[INCIDENCIAS[c] for c in columnas], barmode="group")
        fig.update_layout(legend_title_text=None, yaxis_title="Interacciones", xaxis_title="Fecha")
        st.plotly_chart(fig, width="stretch", key="incidencias_diarias")
    else:
        st.info("No hay incidencias diarias en el rango seleccionado.")
    linea_diaria(diarias, ["tasa_incidencias_pct"], "Porcentaje diario de interacciones con incidencia")
    with st.expander("Calidad y cobertura de los datos · histórico"):
        calidad = tabla([
            {"control": k.replace("_", " ").capitalize(), "cantidad": v}
            for k, v in metricas.get("calidad_datos", {}).items()
        ])
        st.dataframe(calidad, width="stretch", hide_index=True)


def vista_detalle(metricas):
    st.subheader("Detalle de conversaciones · solo administradores")
    try:
        mensajes = cargar_mensajes(metricas.get("generado_en", ""))
    except ClientError as error:
        if es_ausente(error):
            st.info("Publica mensajes.parquet desde la última sección del notebook para consultar el detalle.")
        else:
            st.error("No se pudo leer el detalle de conversaciones en MinIO. Revisa los permisos del servicio.")
        return
    except BotoCoreError:
        st.error("No se pudo conectar con MinIO para leer las conversaciones.")
        return
    if mensajes.is_empty():
        st.info("No hay conversaciones disponibles.")
        return

    usuarios = sorted(mensajes["usuario_cedula"].drop_nulls().cast(pl.String).unique().to_list())
    mensajes = mensajes.with_columns(pl.col("usuario_cedula").cast(pl.String))
    elegidos = st.multiselect("Usuarios", usuarios, key="detalle_usuarios")
    if elegidos:
        mensajes = mensajes.filter(pl.col("usuario_cedula").is_in(elegidos))
    tipos = {"Todas": None, "Sin respuesta": "hay_respuesta", "Con incidencia": "tiene_incidencia", "Con herramientas": "usa_tool"}
    tipos = {k: v for k, v in tipos.items() if v is None or v in mensajes.columns}
    tipo = st.selectbox("Interacciones", list(tipos), key="detalle_tipo")
    if tipos[tipo]:
        condicion = pl.col(tipos[tipo]).fill_null(False)
        mensajes = mensajes.filter(~condicion if tipo == "Sin respuesta" else condicion)
    buscar = st.text_input("Buscar en mensajes y respuestas", key="detalle_buscar").strip()
    if buscar:
        mensajes = mensajes.filter(
            pl.col("content").fill_null("").str.to_lowercase().str.contains(buscar.lower(), literal=True)
            | pl.col("respuesta_ia").fill_null("").str.to_lowercase().str.contains(buscar.lower(), literal=True)
        )
    if "created_at" in mensajes.columns:
        mensajes = mensajes.sort("created_at", descending=True, nulls_last=True)
    limite = st.select_slider("Filas a mostrar", options=[50, 100, 200, 500, 1000, 2000], value=200, key="detalle_limite")
    campos = [
        "created_at", "usuario_cedula", "session_id", "alias_sesion", "content",
        "respuesta_ia", "hay_respuesta", "response_latency_s", "sentiment", "usa_tool", "tools", "error",
    ]
    visible = mensajes.select([c for c in campos if c in mensajes.columns])
    st.caption(f"{numero(mensajes.height)} coincidencias · mostrando {numero(min(limite, mensajes.height))} filas. La búsqueda abarca todo el histórico.")
    st.dataframe(
        visible.head(limite), width="stretch", hide_index=True,
        column_config={
            "content": st.column_config.TextColumn("Mensaje del usuario", width="large"),
            "respuesta_ia": st.column_config.TextColumn("Respuesta", width="large"),
            "response_latency_s": st.column_config.NumberColumn("Latencia (s)", format="%.2f"),
        },
    )
    st.download_button(
        "Descargar coincidencias (CSV)", data=visible.write_csv(),
        file_name="chatbot_th_conversaciones.csv", mime="text/csv", key="descargar_detalle",
    )


def main():
    st.set_page_config(page_title="Chatbot TH · Analítica", layout="wide")
    username, role = login_gate()
    st.title("Chatbot TH · Panel de analítica")
    st.caption(f"Sesión: {username} ({role})")
    if st.sidebar.button("Actualizar datos", key="actualizar_datos"):
        cargar_metricas.clear()
        cargar_mensajes.clear()
    try:
        metricas = cargar_metricas()
    except ClientError as error:
        if es_ausente(error):
            st.warning("Todavía no hay resultados publicados. Ejecuta la sección Publicar resultados gold en MinIO del notebook 2_analysis.ipynb.")
        else:
            st.error("No se pudieron leer las métricas en MinIO. Revisa los permisos del servicio.")
        st.stop()
    except BotoCoreError:
        st.error("No se pudo conectar con MinIO. Revisa la conexión del servicio.")
        st.stop()
    except KeyError:
        st.error("Falta la configuración de conexión a MinIO del dashboard.")
        st.stop()
    except (ValueError, UnicodeDecodeError):
        st.error("El archivo de métricas no tiene un formato válido. Vuelve a publicar los resultados del notebook.")
        st.stop()

    nueva_version = metricas.get("version_esquema", 1) >= 2
    zona = metricas.get("zona_horaria", "UTC")
    st.sidebar.caption(f"Actualizado: {fecha_generacion(metricas.get('generado_en'), zona)}")
    st.sidebar.caption(f"Zona horaria: {zona}")
    if not nueva_version:
        st.warning("Se está mostrando el formato anterior de resultados. Publica los archivos gold del notebook actualizado para habilitar todas las vistas.")

    vistas = ["Resumen", "Conversaciones", "Herramientas", "Rendimiento", "Incidencias"]
    if role == "admin":
        vistas.append("Detalle")
    vista = st.sidebar.radio("Vista", vistas, key="vista")
    top_n = st.sidebar.slider("Elementos por ranking", 5, 20, 15, key="top_n")
    actividad = actividad_historica(metricas)
    periodo = None
    if vista in {"Resumen", "Rendimiento", "Incidencias"} and not actividad.is_empty():
        fechas = [date.fromisoformat(x) for x in actividad["fecha"].drop_nulls().to_list()]
        if fechas:
            minimo, maximo = min(fechas), max(fechas)
            seleccion = st.sidebar.date_input(
                "Fechas para gráficas diarias", value=(minimo, maximo),
                min_value=minimo, max_value=maximo, key="periodo_diario",
            )
            if len(seleccion) == 2:
                periodo = seleccion
            else:
                st.sidebar.info("Completa el rango para filtrar las gráficas diarias.")
            st.sidebar.caption("El rango filtra las gráficas diarias. Los KPIs y rankings muestran el histórico completo.")
    actividad = filtrar_fechas(actividad, periodo)

    for columna, (etiqueta, valor) in zip(st.columns(4), [
        ("Interacciones", metricas.get("total_interacciones", metricas.get("total_mensajes"))),
        ("Respuestas", metricas.get("total_respuestas")),
        ("Usuarios únicos", metricas.get("total_usuarios")),
        ("Sesiones", metricas.get("total_sesiones")),
    ]):
        columna.metric(etiqueta, numero(valor))
    st.caption("Histórico completo")
    st.divider()

    if not nueva_version and vista not in {"Resumen", "Detalle"}:
        st.info("Esta vista estará disponible al publicar los nuevos resultados gold desde el notebook.")
        return
    if vista == "Resumen":
        vista_resumen(metricas, actividad, top_n)
    elif vista == "Conversaciones":
        vista_conversaciones(metricas, top_n)
    elif vista == "Herramientas":
        vista_herramientas(metricas, top_n)
    elif vista == "Rendimiento":
        vista_rendimiento(metricas, actividad, top_n)
    elif vista == "Incidencias":
        vista_incidencias(metricas, periodo)
    elif vista == "Detalle" and role == "admin":
        vista_detalle(metricas)


if __name__ == "__main__":
    main()
