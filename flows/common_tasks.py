"""
Tareas compartidas de Prefect: conexión a PostgreSQL, IBM DB2 y MinIO (S3).
===========================================================================

Vive en `flows/` (git, montado como /flows/org en prefect/prefect-worker
y /srv/flows/org en jupyterhub) porque es infraestructura reutilizada por
TODOS los flows del proyecto, no un experimento de un usuario.

Uso desde cualquier flow (org, shared o de un usuario en /flows/users):

    from common_tasks import connect_postgres, conectar_minio, leer_query, \
        ejecutar_escritura, connect_db2, cerrar_conexion_db2, leer_query_db2, \
        descargar_archivo_minio, subir_dataframe_archivo

Esto funciona sin imports relativos porque /flows/org está en PYTHONPATH
(ver PYTHONPATH en docker-compose.yml y jupyterhub_config.py).

`descargar_archivo_minio`/`subir_dataframe_archivo` manejan JSON en dos
formas, según el contenido, no según un flag aparte -- la extensión .json de
la key es lo que decide cómo se lee/escribe, así que debe coincidir con lo
que subiste:
- Un DataFrame con formato="json" se guarda como lista de registros
  (orient="records") y se descarga con engine="pandas"/"polars".
- Un dict (ej. un diccionario de métricas) se guarda como objeto JSON suelto
  y se descarga con engine="dict", que devuelve el dict tal cual.

DB2 requiere el paquete `ibm_db`, que todavía no está instalado en
jupyterhub/Dockerfile ni prefect-worker/Dockerfile -- agrégalo y reconstruye
las imágenes antes de usar `connect_db2`/`leer_query_db2` (ver el import
perezoso más abajo, que evita que esto rompa el resto del módulo mientras
tanto).
"""

import json
import os

import boto3
import pandas as pd
import polars as pl
import psycopg2
from prefect import task
from prefect.cache_policies import NO_CACHE
import openpyxl

POSTGRES_HOST = os.getenv("POSTGRES_HOST", "pgbouncer")
POSTGRES_USER = os.getenv("POSTGRES_USER")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD")
POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")

# Valores por defecto para IBM DB2. Para credenciales por proyecto (ej. un
# usuario/password de DB2 distinto para el chat de TH vs. académico), no se
# hardcodea el sufijo acá -- cada flow resuelve su propia variable con sufijo
# (ej. `os.getenv("DB2_USER_TH") or DB2_USER`, mismo patrón que OPENAI_API_KEY_TH
# en analisis_chat_th.py) y se la pasa explícita a `connect_db2(user=..., password=...)`.
DB2_HOST = os.getenv("DB2_HOST")
DB2_PORT = os.getenv("DB2_PORT", "50000")
DB2_USER = os.getenv("DB2_USER")
DB2_PASSWORD = os.getenv("DB2_PASSWORD")
DB2_DATABASE = os.getenv("DB2_DATABASE_SAAC")

MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "http://minio:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY")


@task(name="Conectar PostgreSQL", cache_policy=NO_CACHE)
def connect_postgres(database: str):
    """Conectar a PostgreSQL. `database` es obligatorio: cada equipo/flow usa su propia base."""
    try:
        conexion = psycopg2.connect(
            host=POSTGRES_HOST,
            database=database,
            user=POSTGRES_USER,
            password=POSTGRES_PASSWORD,
            port=POSTGRES_PORT,
        )
        print(f"✓ Conexión a PostgreSQL establecida: {POSTGRES_HOST}/{database}")
        return conexion
    except Exception as e:
        raise RuntimeError(f"Error conectando a PostgreSQL: {e}")


@task(name="Cerrar conexión PostgreSQL", cache_policy=NO_CACHE)
def cerrar_conexion(conexion):
    if conexion:
        conexion.close()
        print("✓ Conexión PostgreSQL cerrada")


@task(name="Leer query PostgreSQL", cache_policy=NO_CACHE)
def leer_query(conexion, query: str, engine: str = "pandas"):
    """
    Ejecutar un SELECT y devolver un DataFrame.

    Args:
        conexion: Conexión psycopg2 (de `connect_postgres`)
        query: Sentencia SELECT
        engine: "pandas" (por defecto) o "polars" -- qué tipo de DataFrame devolver.

    Returns:
        DataFrame (pandas o polars según `engine`) con el resultado.
    """
    if engine not in ("pandas", "polars"):
        raise ValueError(f"engine no soportado: {engine!r} (usa 'pandas' o 'polars')")

    try:
        if engine == "polars":
            # Directo del cursor (fetchall + nombres de columna), sin pasar por
            # pandas primero -- convertir después de leer con pandas no ahorra
            # memoria ni tiempo, solo duplica el trabajo.
            with conexion.cursor() as cursor:
                cursor.execute(query)
                columnas = [descripcion[0] for descripcion in cursor.description]
                filas = cursor.fetchall()
            df = pl.DataFrame(filas, schema=columnas, orient="row")
        else:
            df = pd.read_sql_query(query, conexion)
        print(f"✓ Leídas {len(df)} filas ({engine})")
        return df
    except Exception as e:
        raise RuntimeError(f"Error leyendo datos: {e}")


@task(name="Ejecutar escritura PostgreSQL (INSERT/UPDATE/DELETE)", cache_policy=NO_CACHE)
def ejecutar_escritura(conexion, query: str, params=None, many: bool = False) -> int:
    """
    Ejecutar un INSERT, UPDATE o DELETE y hacer commit. Sirve para los tres
    porque la única diferencia entre ellos es el texto de la sentencia SQL
    que se le pasa -- no hay una task separada por verbo.

    Args:
        conexion: Conexión psycopg2 (de `connect_postgres`)
        query: Sentencia SQL con placeholders `%s`, ej.
            "INSERT INTO tabla (a, b) VALUES (%s, %s)" o
            "UPDATE tabla SET a = %s WHERE id = %s" o
            "DELETE FROM tabla WHERE id = %s"
        params: Tupla de valores para un solo statement, o lista de tuplas
            si `many=True` (ej. para insertar/actualizar varias filas de una).
        many: Si True, ejecuta `executemany(query, params)` -- `params` debe
            ser una lista de tuplas.

    Returns:
        Número de filas afectadas.
    """
    try:
        with conexion.cursor() as cursor:
            if many:
                cursor.executemany(query, params or [])
            else:
                cursor.execute(query, params)
            filas_afectadas = cursor.rowcount
        conexion.commit()
        print(f"✓ Escritura ejecutada: {filas_afectadas} filas afectadas")
        return filas_afectadas
    except Exception as e:
        conexion.rollback()
        raise RuntimeError(f"Error ejecutando escritura: {e}")


def _importar_ibm_db():
    """
    Import perezoso de `ibm_db` (no está instalado todavía en jupyterhub/
    prefect-worker). Se hace acá adentro y no arriba del módulo para que
    `common_tasks.py` siga importando bien para TODOS los demás flows aunque
    el paquete/Dockerfiles todavía no se hayan reconstruido -- un `import
    ibm_db` a nivel de módulo rompería `from common_tasks import ...` para
    cualquier flow, no solo para el que usa DB2.
    """
    try:
        import ibm_db
    except ImportError as e:
        raise RuntimeError(
            "El paquete 'ibm_db' no está instalado. Agrégalo a "
            "jupyterhub/Dockerfile y prefect-worker/Dockerfile y reconstruye "
            "las imágenes (docker compose build jupyterhub prefect-worker-chats "
            "prefect-worker-training prefect-worker-dashboards prefect-worker-default)."
        ) from e
    return ibm_db


@task(name="Conectar IBM DB2", cache_policy=NO_CACHE)
def connect_db2(database: str = None, host: str = None, port: str = None, user: str = None, password: str = None):
    """
    Conectar a IBM DB2. Todos los argumentos son opcionales: si no se pasan,
    se usan las variables de entorno genéricas DB2_HOST/DB2_PORT/DB2_USER/
    DB2_PASSWORD/DB2_DATABASE. Para credenciales propias de un proyecto, pasa
    `user`/`password` (y `host`/`port`/`database` si también cambian) leídos
    por el flow desde variables con sufijo, ej.:

        connect_db2(
            database="ESPOL",
            user=os.getenv("DB2_USER_TH") or os.getenv("DB2_USER"),
            password=os.getenv("DB2_PASSWORD_TH") or os.getenv("DB2_PASSWORD"),
        )
    """
    ibm_db = _importar_ibm_db()

    host = host or DB2_HOST
    port = port or DB2_PORT
    user = user or DB2_USER
    password = password or DB2_PASSWORD
    database = database or DB2_DATABASE

    conn_str = f"DATABASE={database};HOSTNAME={host};PORT={port};PROTOCOL=TCPIP;UID={user};PWD={password};"
    try:
        conexion = ibm_db.connect(conn_str, "", "")
        print(f"✓ Conexión a DB2 establecida: {host}/{database}")
        return conexion
    except Exception as e:
        raise RuntimeError(f"Error conectando a DB2: {e}")


@task(name="Cerrar conexión DB2", cache_policy=NO_CACHE)
def cerrar_conexion_db2(conexion):
    """`ibm_db` no expone `.close()` en la conexión (no es DBAPI2 estándar como psycopg2) -- se cierra con `ibm_db.close(...)`."""
    if conexion:
        ibm_db = _importar_ibm_db()
        ibm_db.close(conexion)
        print("✓ Conexión DB2 cerrada")


@task(name="Leer query DB2", cache_policy=NO_CACHE)
def leer_query_db2(conexion, query: str, engine: str = "pandas"):
    """
    Ejecutar un SELECT en DB2 y devolver un DataFrame.

    `ibm_db` no implementa el DBAPI2 estándar (no hay `cursor.description`/
    `fetchall`), así que se arma el DataFrame a mano fila por fila con
    `fetch_assoc`, igual que se venía haciendo antes de esta task.

    Args:
        conexion: Conexión de `connect_db2`
        query: Sentencia SELECT
        engine: "pandas" (por defecto) o "polars"

    Returns:
        DataFrame (pandas o polars según `engine`) con el resultado.
    """
    if engine not in ("pandas", "polars"):
        raise ValueError(f"engine no soportado: {engine!r} (usa 'pandas' o 'polars')")

    ibm_db = _importar_ibm_db()

    try:
        stmt = ibm_db.exec_immediate(conexion, query)
        filas = []
        fila = ibm_db.fetch_assoc(stmt)
        while fila:
            filas.append(fila)
            fila = ibm_db.fetch_assoc(stmt)

        df = pl.DataFrame(filas) if engine == "polars" else pd.DataFrame(filas)
        print(f"✓ Leídas {len(df)} filas de DB2 ({engine})")
        return df
    except Exception as e:
        raise RuntimeError(f"Error leyendo datos de DB2: {e}")


@task(name="Conectar S3 (MinIO)", cache_policy=NO_CACHE)
def conectar_minio():
    s3 = boto3.client(
        "s3",
        endpoint_url=MINIO_ENDPOINT,
        aws_access_key_id=MINIO_ACCESS_KEY,
        aws_secret_access_key=MINIO_SECRET_KEY,
    )
    print(f"✓ Conexión a MinIO: {MINIO_ENDPOINT}")
    return s3


_LECTORES = {
    "pandas": {".csv": pd.read_csv, ".xlsx": pd.read_excel, ".parquet": pd.read_parquet, ".json": pd.read_json},
    "polars": {".csv": pl.read_csv, ".xlsx": pl.read_excel, ".parquet": pl.read_parquet, ".json": pl.read_json},
}


@task(name="Descargar CSV, XLSX, Parquet o JSON (DataFrame o dict) desde MinIO", cache_policy=NO_CACHE)
def descargar_archivo_minio(s3_client, bucket: str, key: str, engine: str = "pandas"):
    """
    Descargar un CSV, XLSX, Parquet o JSON de MinIO.

    Args:
        s3_client: Cliente boto3 S3 (MinIO)
        bucket: Nombre del bucket
        key: Ruta del archivo dentro del bucket
        engine: "pandas" (por defecto), "polars" o "dict".
            "pandas"/"polars" -- qué tipo de DataFrame devolver. Para CSV/XLSX/
            Parquet, o para un JSON que es una lista de registros tabulares
            (ej. lo que sube `subir_dataframe_archivo` con formato="json").
            `polars-lts-cpu` ya está instalado en jupyterhub y prefect-worker,
            así que "polars" funciona hoy mismo, no es solo preparación a futuro.
            "dict" -- solo válido con archivos .json que NO son una lista de
            registros sino un objeto JSON suelto (ej. un diccionario de
            métricas como gold/th/chatbot/metrics.json, subido con
            `subir_dataframe_archivo(..., df=metricas_dict, formato="json")`).
            Devuelve el dict tal cual, sin intentar armar un DataFrame.

    Returns:
        DataFrame (pandas o polars) si engine es "pandas"/"polars", o un
        dict si engine="dict". Vacío ({} o DataFrame vacío) si no existe.
    """
    if engine not in ("pandas", "polars", "dict"):
        raise ValueError(f"engine no soportado: {engine!r} (usa 'pandas', 'polars' o 'dict')")

    extension = os.path.splitext(key)[1]
    if engine == "dict" and extension != ".json":
        raise ValueError(f"engine='dict' solo aplica a archivos .json (key={key!r})")

    local_file = f"/tmp/{os.path.basename(key)}"
    valor_vacio = {} if engine == "dict" else (pd.DataFrame() if engine == "pandas" else pl.DataFrame())
    try:
        s3_client.download_file(bucket, key, local_file)

        if engine == "dict":
            with open(local_file, "r", encoding="utf-8") as f:
                valor = json.load(f)
            os.remove(local_file)
            if not isinstance(valor, dict):
                raise ValueError(
                    f"s3://{bucket}/{key} no contiene un objeto JSON (dict) sino {type(valor).__name__} "
                    "-- usa engine='pandas'/'polars' para una lista de registros"
                )
            print(f"✓ Descargado s3://{bucket}/{key} (dict): {len(valor)} claves")
            return valor

        lector = _LECTORES[engine].get(extension)
        if lector is None:
            raise ValueError(f"Formato no soportado para el archivo: {key}")
        df = lector(local_file)
        os.remove(local_file)
        print(f"✓ Descargado s3://{bucket}/{key} ({engine}): {len(df)} registros")
        return df
    except s3_client.exceptions.NoSuchKey:
        print(f"⚠️  No existe s3://{bucket}/{key}, devolviendo {'dict' if engine == 'dict' else 'DataFrame'} vacío")
        return valor_vacio
    except Exception as e:
        print(f"⚠️  Error descargando s3://{bucket}/{key}: {e}, devolviendo {'dict' if engine == 'dict' else 'DataFrame'} vacío")
        return valor_vacio


@task(name="Subir DataFrame o dict como CSV, XLSX, Parquet o JSON a MinIO", cache_policy=NO_CACHE)
def subir_dataframe_archivo(s3_client, df, bucket: str, key: str, formato: str = "csv"):
    """
    Subir un DataFrame (pandas o polars, detectado automáticamente) como
    CSV/XLSX/Parquet/JSON, o un dict como JSON, a MinIO. Si está vacío, no
    hace nada.

    Args:
        s3_client: Cliente boto3 S3 (MinIO)
        df: DataFrame a subir (pandas.DataFrame o polars.DataFrame), o un
            dict si formato="json" (ej. un diccionario de métricas -- se
            guarda como objeto JSON suelto, no como lista de registros).
        bucket: Nombre del bucket
        key: Ruta del archivo dentro del bucket. La extensión debe coincidir
            con `formato` (ej. `.json` para formato="json") -- es la
            extensión, no `formato`, lo que decide cómo se lee después con
            `descargar_archivo_minio`.
        formato: "csv", "xlsx", "parquet" o "json" (por defecto "csv"). "xlsx" con un
            DataFrame de polars requiere el paquete `xlsxwriter` (no instalado
            todavía) -- usa "csv" o "parquet" con polars hasta agregarlo.
            Un DataFrame con formato="json" se guarda como lista de registros
            (orient="records"); descárgalo con `engine="pandas"/"polars"`. Un
            dict con formato="json" se guarda como objeto JSON suelto;
            descárgalo con `engine="dict"`.

    Returns:
        None
    """
    es_dict = isinstance(df, dict)
    es_polars = isinstance(df, pl.DataFrame)

    if es_dict:
        if formato != "json":
            raise ValueError(f"Un dict solo se puede subir con formato='json' (recibido formato={formato!r})")
        vacio = not df
    else:
        vacio = df.is_empty() if es_polars else df.empty

    if vacio:
        print(f"⚠️  {'Dict' if es_dict else 'DataFrame'} vacío, no se sube")
        return

    local_file = f"/tmp/{os.path.basename(key)}"
    try:
        if es_dict:
            with open(local_file, "w", encoding="utf-8") as f:
                json.dump(df, f, ensure_ascii=False, indent=2)
        else:
            if es_polars:
                escritores = {
                    "csv": df.write_csv,
                    "parquet": df.write_parquet,
                    "xlsx": df.write_excel,
                    "json": df.write_json,
                }
            else:
                escritores = {
                    "csv": lambda p: df.to_csv(p, index=False),
                    "xlsx": lambda p: df.to_excel(p, index=False),
                    "parquet": lambda p: df.to_parquet(p, index=False),
                    "json": lambda p: df.to_json(p, orient="records", force_ascii=False, indent=2),
                }
            escritor = escritores.get(formato)
            if escritor is None:
                raise ValueError(f"Formato no soportado: {formato}")
            escritor(local_file)

        s3_client.upload_file(local_file, bucket, key)
        os.remove(local_file)
        tipo = "dict" if es_dict else ("polars" if es_polars else "pandas")
        detalle = f"{len(df)} claves" if es_dict else f"{len(df)} registros"
        print(f"✓ Subido a s3://{bucket}/{key} ({tipo}): {detalle}")
    except Exception as e:
        print(f"✗ Error subiendo a s3://{bucket}/{key}: {e}")
        raise
