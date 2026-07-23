"""
Flow: Análisis de Chat TH (Talento Humano)
==========================================

Procesa mensajes de chat para:
1. Análisis de sentimientos
2. Clasificación de herramientas (tools)
3. Generación de reportes

Ejecuta diariamente en el servidor Linux.
Lectura: PostgreSQL → Procesamiento → Guardado: S3 (MinIO) + Excel
"""

import os
import pandas as pd
import json
from datetime import datetime
from dotenv import load_dotenv
from prefect import flow, task
from prefect.cache_policies import NO_CACHE
from openai import OpenAI
from transformers import AutoTokenizer, AutoModelForSequenceClassification
import torch

from common_tasks import (
    connect_postgres,
    cerrar_conexion,
    conectar_minio,
    descargar_archivo_minio,
    subir_dataframe_archivo,
)


# ============================================================================
# CONFIGURACIÓN
# ============================================================================

# Cargar variables de entorno
load_dotenv()

# Conexión a Postgres/MinIO ahora vive en common_tasks.py (import de arriba);
# aquí solo queda lo específico de este flow.
OPENAI_API_KEY = (
    os.getenv("OPENAI_API_KEY_TH")
    or os.getenv("OPENAI_API_KEY")
    or os.getenv("OPEN_API_KEY")
)

# Constantes
MODELO_SENTIMIENTOS = "tabularisai/multilingual-sentiment-analysis"
BATCH_SIZE = 20
MAX_RETRIES: int = 3
RETRY_DELAY: int = 5 * 60  # 5 minutos (en segundos)


# ============================================================================
# TAREAS (TASKS)
# ============================================================================

@task(name="Leer mensajes de chat desde DB", retries=MAX_RETRIES, retry_delay_seconds=RETRY_DELAY, cache_policy=NO_CACHE)
def leer_mensajes_chat(conexion):
    """Leer mensajes de chat desde PostgreSQL"""
    query = """
    SELECT
        m.*,
        s.usuario_cedula,
        s.alias_sesion,
        s.model_used,
        s.regimenes
    FROM "TH".chat_mensajes m
    INNER JOIN "TH".chat_sesiones s
        ON m.session_id = s.session_id
    WHERE s.usuario_cedula <> '0922663208'
      AND m.role <> 'tool'
    ORDER BY m.created_at;
    """
    
    try:
        df = pd.read_sql_query(query, conexion)
        print(f"✓ Leídos {len(df)} mensajes desde PostgreSQL")
        return df
    except Exception as e:
        raise RuntimeError(f"Error leyendo mensajes: {e}")


@task(name="Filtrar mensajes nuevos", cache_policy=NO_CACHE)
def filtrar_mensajes_nuevos(df_mensajes, df_anterior):
    """Filtrar solo mensajes nuevos (no procesados antes)"""
    if df_anterior.empty:
        return df_mensajes.copy()
    
    df_nuevos = df_mensajes[
        ~df_mensajes['id'].isin(df_anterior['id'])
    ].copy()
    
    print(f"✓ Mensajes nuevos: {len(df_nuevos)} (Total: {len(df_mensajes)})")
    return df_nuevos


@task(name="Procesar pares human-AI", cache_policy=NO_CACHE)
def procesar_pares_human_ai(df):
    """Asociar mensajes humanos con respuestas de IA"""
    if df.empty:
        return df
    
    df = (
        df.sort_values("created_at")
        .reset_index()
        .rename(columns={"index": "indice_original"})
        .copy()
    )
    
    # Filtrar solo human y AI
    df = df[df["role"].isin(["human", "ai"])].copy()
    
    # Asociar siguiente mensaje
    df["siguiente_role"] = df.groupby("session_id")["role"].shift(-1)
    df["siguiente_content"] = df.groupby("session_id")["content"].shift(-1)
    
    # Filtrar solo mensajes humanos
    df_human = df[df["role"] == "human"].copy()
    df_human["respuesta_ia"] = (
        df_human["siguiente_content"]
        .where(df_human["siguiente_role"] == "ai")
    )
    
    print(f"✓ Pares procesados: {len(df_human)} mensajes humanos")
    return df_human


@task(name="Análisis de Sentimientos", cache_policy=NO_CACHE)
def analizar_sentimientos(df):
    """Analizar sentimientos usando modelo multilingüe"""
    if df.empty:
        return df
    
    print(f"Cargando modelo: {MODELO_SENTIMIENTOS}")
    tokenizer = AutoTokenizer.from_pretrained(MODELO_SENTIMIENTOS)
    model = AutoModelForSequenceClassification.from_pretrained(MODELO_SENTIMIENTOS)
    
    def predict_sentiment(texts):
        inputs = tokenizer(
            texts,
            return_tensors="pt",
            truncation=True,
            padding=True,
            max_length=512
        )
        with torch.no_grad():
            outputs = model(**inputs)
        probabilities = torch.nn.functional.softmax(outputs.logits, dim=-1)
        sentiment_map = {
            0: "Very Negative",
            1: "Negative",
            2: "Neutral",
            3: "Positive",
            4: "Very Positive"
        }
        return [sentiment_map[p] for p in torch.argmax(probabilities, dim=-1).tolist()]
    
    texts = df["content"].to_list()
    sentiments = predict_sentiment(texts)
    
    df["sentiment"] = sentiments
    print(f"✓ Sentimientos analizados: {len(df)} mensajes")
    
    # Mostrar distribución
    print("\n📊 Distribución de sentimientos:")
    print(df["sentiment"].value_counts())
    
    return df


PROMPT_CLASIFICAR_TOOL_BATCH = """
You are a strict intent router for the ESPOL Human Talent chatbot.

Task:
Analyze each Spanish user message independently and determine which available
tools can resolve the user's explicit or clearly actionable requests.

The input will be a JSON array with this structure:

[
    {
        "id": 0,
        "mensaje": "user message"
    }
]

You must analyze every message independently.

Output constraints:

1. Output only one valid RAW JSON array.
2. Return exactly one result for every input message.
3. Preserve the same "id" received in the input.
4. Preserve the same order as the input.
5. Each result must have exactly these properties:

   * "id": integer
   * "usa_tool": boolean
   * "tools": array

6. Set "usa_tool" to true when at least one available tool can resolve
   at least one explicit or clearly actionable user request.

7. Set "usa_tool" to false when none of the available tools can resolve
   the message.

8. When "usa_tool" is false, "tools" must be an empty array.

9. When "usa_tool" is true, "tools" must contain one or more allowed tool names.

10. Include only real tool names listed in "Allowed tools".

11. Do not repeat the same tool more than once.

12. Preserve the order in which the user's requests appear.

13. Analyze each message independently.
    Never use information from one message to classify another message.

14. Do not combine results from different messages.

Intent rules:

15. Select a tool only when the user is currently asking the chatbot to perform,
retrieve, verify, explain, generate, update, or consult something supported
by that tool.

16. Do not select a tool merely because the message contains a keyword
related to a tool.

17. A single isolated word, noun, topic, position name, document name,
or person name is not sufficient by itself to trigger a tool when
the user's intention is unclear.

18. Short messages can trigger a tool only when they express a clear
question, command, or actionable request.

19. If the message is ambiguous and does not contain a clear request
or question, return usa_tool=false and tools=[].

20. Do not infer unsupported intentions from vague or incomplete messages.

21. Past statements, examples, quoted text, hypothetical scenarios,
or descriptions of previous requests must not trigger a tool unless
they also contain a current supported request.

22. When multiple supported requests appear in the same message,
include all corresponding tools once, preserving request order.

Allowed tools:

* Tool - get novedad
* Tool - get subrogantes
* Tool - get antiguedad
* Tool - get subrogante cargo
* Tool - agente normativa
* Tool - generate cv
* Tool - get autoridad
* Tool - get autoridad by name
* Tool - update document
* Tool - update alias

Tool definitions:

* Tool - get novedad
  Use when the current user explicitly asks about their own pending novelty,
  novelty status, deadline, or whether they currently have a novelty.

* Tool - get subrogantes
  Use when the user requests the general or complete list of current
  substitutions or subrogations.

* Tool - get antiguedad
  Use when the current user asks about their own employment seniority,
  years worked, length of service, or institutional tenure.

* Tool - get subrogante cargo
  Use when the user asks who is temporarily substituting or subrogating
  a specific position, role, or unit.

* Tool - agente normativa
  Use when the user asks a question about Human Talent policies, laws,
  institutional rules, requirements, procedures, benefits, permissions,
  vacations, licenses, or steps to follow.

* Tool - generate cv
  Use when the current user explicitly asks to generate, create, produce,
  prepare, or download their CV.

* Tool - get autoridad
  Use when the user asks who currently holds a specific position
  or authority role.

* Tool - get autoridad by name
  Use when the user provides a person's name and asks about that person's
  position, unit, authority information, or substitution status.

* Tool - update document
  Use when the current user explicitly asks to update their ID card
  document or voting certificate.

* Tool - update alias
  Use when the user explicitly asks to change the name or alias used
  to address them.

Examples:

Input:
[
    {"id": 0, "mensaje": "hola buenos días"},
    {"id": 1, "mensaje": "dime mi antigüedad laboral"},
    {"id": 2, "mensaje": "quién es el rector"},
    {"id": 3, "mensaje": "vacaciones"}
]

Output:
[
    {"id": 0, "usa_tool": false, "tools": []},
    {"id": 1, "usa_tool": true, "tools": ["Tool - get antiguedad"]},
    {"id": 2, "usa_tool": true, "tools": ["Tool - get autoridad"]},
    {"id": 3, "usa_tool": false, "tools": []}
]
"""

TOOLS_PERMITIDAS = {
    "Tool - get novedad",
    "Tool - get subrogantes",
    "Tool - get antiguedad",
    "Tool - get subrogante cargo",
    "Tool - agente normativa",
    "Tool - generate cv",
    "Tool - get autoridad",
    "Tool - get autoridad by name",
    "Tool - update document",
    "Tool - update alias",
}


def _clasificar_tools_batch(client, mensajes):
    """Clasifica un batch de mensajes usando la Responses API de OpenAI (igual que el notebook)"""
    if not mensajes:
        return []

    input_data = [
        {"id": i, "mensaje": mensaje}
        for i, mensaje in enumerate(mensajes)
    ]

    response = client.responses.create(
        model="gpt-5.4-nano",
        instructions=PROMPT_CLASIFICAR_TOOL_BATCH,
        input=json.dumps(input_data, ensure_ascii=False),
        temperature=0,
        max_output_tokens=max(500, len(mensajes) * 50),
    )

    texto_respuesta = response.output_text.strip()

    try:
        resultados = json.loads(texto_respuesta)
    except json.JSONDecodeError as error:
        raise ValueError(
            f"El modelo no devolvió JSON válido: {texto_respuesta!r}"
        ) from error

    if not isinstance(resultados, list):
        raise ValueError("La respuesta debe ser una lista JSON.")

    if len(resultados) != len(mensajes):
        raise ValueError(
            f"Se enviaron {len(mensajes)} mensajes pero se recibieron {len(resultados)} resultados."
        )

    resultados_validados = []

    for esperado_id, resultado in enumerate(resultados):
        if not isinstance(resultado, dict):
            raise ValueError(f"El resultado {esperado_id} no es un objeto.")

        if set(resultado.keys()) != {"id", "usa_tool", "tools"}:
            raise ValueError(f"Estructura incorrecta en resultado {esperado_id}: {resultado}")

        id_resultado = resultado["id"]
        usa_tool = resultado["usa_tool"]
        tools = resultado["tools"]

        if id_resultado != esperado_id:
            raise ValueError(
                f"ID inesperado. Esperado: {esperado_id}, recibido: {id_resultado}"
            )

        if not isinstance(usa_tool, bool):
            raise ValueError('"usa_tool" debe ser booleano.')

        if not isinstance(tools, list):
            raise ValueError('"tools" debe ser una lista.')

        tools = list(dict.fromkeys(tools))

        tools_invalidas = [tool for tool in tools if tool not in TOOLS_PERMITIDAS]
        if tools_invalidas:
            raise ValueError(f"Tools no permitidas: {tools_invalidas}")

        if usa_tool != bool(tools):
            raise ValueError(
                f"Inconsistencia en mensaje {esperado_id}: usa_tool={usa_tool}, tools={tools}"
            )

        resultados_validados.append({"usa_tool": usa_tool, "tools": tools})

    return resultados_validados


@task(name="Clasificar Tools con OpenAI", retries=MAX_RETRIES, retry_delay_seconds=RETRY_DELAY, cache_policy=NO_CACHE)
def clasificar_tools(df):
    """Clasificar qué herramientas puede resolver cada mensaje (mismo flujo que el notebook)"""
    if df.empty:
        return df

    if not OPENAI_API_KEY:
        print("⚠️  No hay OPENAI_API_KEY, omitiendo clasificación de tools")
        df["usa_tool"] = False
        df["tools"] = [[] for _ in range(len(df))]
        return df

    client = OpenAI(api_key=OPENAI_API_KEY)

    df = df.copy()
    total_original = len(df)

    df["_content_key"] = (
        df["content"].fillna("").astype(str).str.strip().str.lower()
    )
    df_unicos = df.drop_duplicates(subset="_content_key", keep="first")
    mensajes_unicos = df_unicos["content"].tolist()

    total_unicos = len(mensajes_unicos)
    print(f"  Mensajes únicos a clasificar: {total_unicos} (duplicados evitados: {total_original - total_unicos})")

    cache_resultados = {}

    for inicio in range(0, total_unicos, BATCH_SIZE):
        fin = min(inicio + BATCH_SIZE, total_unicos)
        batch = mensajes_unicos[inicio:fin]

        print(f"  Clasificando mensajes {inicio + 1}-{fin} de {total_unicos}...")

        try:
            resultados = _clasificar_tools_batch(client, batch)
            for mensaje, resultado in zip(batch, resultados):
                cache_resultados[mensaje] = resultado
        except Exception as e:
            print(f"  ✗ Error en batch de clasificación: {e}")
            for mensaje in batch:
                cache_resultados[mensaje] = {"usa_tool": False, "tools": []}

    df["usa_tool"] = df["content"].map(
        lambda x: cache_resultados.get(str(x), {}).get("usa_tool", False) if pd.notna(x) else False
    )
    df["tools"] = df["content"].map(
        lambda x: cache_resultados.get(str(x), {}).get("tools", []) if pd.notna(x) else []
    )

    df = df.drop(columns=["_content_key"])

    print(f"✓ Tools clasificadas: {df['usa_tool'].sum()} mensajes con herramientas")

    return df


@task(name="Filtrar y limpiar mensajes", cache_policy=NO_CACHE)
def filtrar_mensajes_validos(df):
    """Filtrar mensajes que no son relevantes"""
    if df.empty:
        return df
    
    # Palabras/frases a excluir (igual que el notebook)
    palabras_no = [
        "llamame", "LLAMAME", "llámame", "Llámame por favor",
        "llámame por favor", "dime asi", "me puedes llamar", "cuenta hasta"
    ]

    mensajes_no = [
        "que puedo hacer", "Sí por favor.", "Hola", "Sí, por favor.",
        "si por favor", "listo ayudame", "2+2?",
        "ERROR [23502] [IBM][DB2/AIX64] SQL0407N Assignment of a NULL value to a NOT NULL column \"TBSPACEID=5, TABLEID=1233, COLNO=1\" is not allowed.",
        "ok", "si", "sí", "listo", "ok, gracias", "ok gracias", "ok gracias.",
        "ok, gracias.", "ok gracias!", "ok, gracias!", "ok gracias!!",
        "ok, gracias!!", "ok gracias!!!", "ok, gracias!!!", "gracias", "a",
        "hello", "hazlo", "si hazlo", "sí por favor",
        "ahora me vas a decir papi y tu eres mi mujer", "Dime Churris"
    ]
    mensajes_no_lower = [msg.lower() for msg in mensajes_no]

    # Filtrar
    df_filtrado = df[
        ~df["content"].str.contains("|".join(palabras_no), case=False, na=False)
    ].copy()

    df_filtrado = df_filtrado[
        ~df_filtrado["content"].str.strip().str.lower().isin(mensajes_no_lower)
    ].copy()
    
    print(f"✓ Mensajes después de filtrado: {len(df_filtrado)} (removidos: {len(df) - len(df_filtrado)})")
    
    return df_filtrado


@task(name="Guardar mensajes en Excel", retries=MAX_RETRIES, retry_delay_seconds=RETRY_DELAY, cache_policy=NO_CACHE)
def guardar_mensajes_excel(df, s3_client):
    """Seleccionar columnas relevantes, armar el nombre con timestamp y subir a MinIO como Excel"""
    if df.empty:
        print("⚠️  DataFrame vacío, no se genera Excel")
        return

    timestamp = datetime.now().strftime("%d_%m_%Y_%H_%M_%S")
    nombre_archivo = f"{timestamp}_mensajes_chatbot.xlsx"

    subir_dataframe_archivo(
        s3_client,
        df[["content", "respuesta_ia"]],
        bucket="processed-data",
        key=f"th/mensajes/{nombre_archivo}",
        formato="xlsx",
    )


# ============================================================================
# FLOW PRINCIPAL
# ============================================================================

@flow(
    name="analisis-chat-th",
    description="Análisis de sentimientos y clasificación de tools para chat TH",
    version="1.0",
    # Sin retries a nivel de flow a propósito: cada task de I/O ya reintenta
    # (MAX_RETRIES/RETRY_DELAY). Si se agregan aquí también, un fallo tardío
    # (ej. guardar_mensajes_excel) reintentaría el flow completo desde cero,
    # re-ejecutando clasificar_tools y re-pagando las llamadas a OpenAI.
)
def analisis_chat_th_flow():
    """
    Flow principal: Análisis completo de chat TH
    
    Pasos:
    1. Conectar a PostgreSQL
    2. Leer mensajes nuevos
    3. Análisis de sentimientos
    4. Clasificación de tools (OpenAI)
    5. Filtrado de mensajes válidos
    6. Guardar resultados en S3
    """
    
    # Conectar a servicios (mismos retries que antes, ahora vía .with_options()
    # sobre las tasks compartidas de common_tasks.py en vez de reimplementarlas)
    print("🚀 Iniciando análisis de chat TH...")
    conexion = connect_postgres.with_options(
        retries=MAX_RETRIES, retry_delay_seconds=RETRY_DELAY
    )(database="saacdata")
    s3_client = conectar_minio.with_options(
        retries=MAX_RETRIES, retry_delay_seconds=RETRY_DELAY
    )()

    try:
        # Leer datos
        df_mensajes = leer_mensajes_chat(conexion)
        df_anterior = descargar_archivo_minio.with_options(
            retries=MAX_RETRIES, retry_delay_seconds=RETRY_DELAY
        )(s3_client, bucket="processed-data", key="th/dataframe_completo.csv")
        
        # Filtrar nuevos
        df_nuevos = filtrar_mensajes_nuevos(df_mensajes, df_anterior)
        
        if df_nuevos.empty:
            print("⚠️  No hay mensajes nuevos para procesar")
            return {"status": "no_changes", "mensajes_procesados": 0}
        
        # Procesar
        df_pares = procesar_pares_human_ai(df_nuevos)
        df_sentimientos = analizar_sentimientos(df_pares)
        df_tools = clasificar_tools(df_sentimientos)
        df_filtrado = filtrar_mensajes_validos(df_tools)
        
        # Combinar con histórico
        if not df_anterior.empty:
            df_final = pd.concat(
                [df_anterior, df_filtrado],
                ignore_index=True
            )
        else:
            df_final = df_filtrado
        
        # Guardar
        subir_dataframe_archivo.with_options(
            retries=MAX_RETRIES, retry_delay_seconds=RETRY_DELAY
        )(s3_client, df_final, bucket="processed-data", key="th/dataframe_completo.csv")
        guardar_mensajes_excel(df_filtrado, s3_client)
        
        print(f"\n✅ Análisis completado:")
        print(f"   - Mensajes nuevos: {len(df_nuevos)}")
        print(f"   - Después de filtrado: {len(df_filtrado)}")
        print(f"   - Total histórico: {len(df_final)}")
        
        return {
            "status": "success",
            "mensajes_nuevos": len(df_nuevos),
            "mensajes_procesados": len(df_filtrado),
            "total_historico": len(df_final)
        }
    
    except Exception as e:
        print(f"✗ Error en flow: {e}")
        raise
    
    finally:
        cerrar_conexion(conexion)


# ============================================================================
# EJECUCIÓN LOCAL (para testing)
# ============================================================================

if __name__ == "__main__":
    # Ejecutar localmente (solo para testing)
    result = analisis_chat_th_flow()
    print(f"\n📊 Resultado: {result}")
