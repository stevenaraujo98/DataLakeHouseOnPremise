"""
Tareas compartidas de Prefect: conexión a PostgreSQL y MinIO (S3).
==================================================================

Vive en `flows/` (git, montado como /flows/org en prefect/prefect-worker
y /srv/flows/org en jupyterhub) porque es infraestructura reutilizada por
TODOS los flows del proyecto, no un experimento de un usuario.

Uso desde cualquier flow (org, shared o de un usuario en /flows/users):

    from common_tasks import connect_postgres, conectar_minio, leer_query, \
        descargar_archivo_minio, subir_dataframe_archivo

Esto funciona sin imports relativos porque /flows/org está en PYTHONPATH
(ver PYTHONPATH en docker-compose.yml y jupyterhub_config.py).
"""

import os

import boto3
import pandas as pd
import polars as pl
import psycopg2
from prefect import task
import openpyxl

POSTGRES_HOST = os.getenv("POSTGRES_HOST", "pgbouncer")
POSTGRES_USER = os.getenv("POSTGRES_USER")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD")
POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")

MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "http://minio:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY")


@task(name="Conectar PostgreSQL")
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


@task(name="Cerrar conexión PostgreSQL")
def cerrar_conexion(conexion):
    if conexion:
        conexion.close()
        print("✓ Conexión PostgreSQL cerrada")


@task(name="Leer query PostgreSQL")
def leer_query(conexion, query: str) -> pd.DataFrame:
    """Ejecutar un SELECT y devolver un DataFrame."""
    try:
        df = pd.read_sql_query(query, conexion)
        print(f"✓ Leídas {len(df)} filas")
        return df
    except Exception as e:
        raise RuntimeError(f"Error leyendo datos: {e}")


@task(name="Conectar S3 (MinIO)")
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
    "pandas": {".csv": pd.read_csv, ".xlsx": pd.read_excel, ".parquet": pd.read_parquet},
    "polars": {".csv": pl.read_csv, ".xlsx": pl.read_excel, ".parquet": pl.read_parquet},
}


@task(name="Descargar CSV o XLSX o Parquet desde MinIO")
def descargar_archivo_minio(s3_client, bucket: str, key: str, engine: str = "pandas"):
    """
    Descargar un CSV, XLSX o Parquet de MinIO. Si no existe, devuelve un DataFrame vacío.

    Args:
        s3_client: Cliente boto3 S3 (MinIO)
        bucket: Nombre del bucket
        key: Ruta del archivo dentro del bucket
        engine: "pandas" (por defecto) o "polars" -- qué tipo de DataFrame devolver.
            `polars-lts-cpu` ya está instalado en jupyterhub y prefect-worker,
            así que "polars" funciona hoy mismo, no es solo preparación a futuro.

    Returns:
        DataFrame (pandas o polars según `engine`) con los datos, o vacío si no existe.
    """
    if engine not in ("pandas", "polars"):
        raise ValueError(f"engine no soportado: {engine!r} (usa 'pandas' o 'polars')")

    local_file = f"/tmp/{os.path.basename(key)}"
    df_vacio = pd.DataFrame() if engine == "pandas" else pl.DataFrame()
    try:
        s3_client.download_file(bucket, key, local_file)
        lector = _LECTORES[engine].get(os.path.splitext(key)[1])
        if lector is None:
            raise ValueError(f"Formato no soportado para el archivo: {key}")
        df = lector(local_file)
        os.remove(local_file)
        print(f"✓ Descargado s3://{bucket}/{key} ({engine}): {len(df)} registros")
        return df
    except s3_client.exceptions.NoSuchKey:
        print(f"⚠️  No existe s3://{bucket}/{key}, devolviendo DataFrame vacío")
        return df_vacio
    except Exception as e:
        print(f"⚠️  Error descargando s3://{bucket}/{key}: {e}, devolviendo DataFrame vacío")
        return df_vacio


@task(name="Subir DataFrame como CSV, XLSX o Parquet a MinIO")
def subir_dataframe_archivo(s3_client, df, bucket: str, key: str, formato: str = "csv"):
    """
    Subir un DataFrame (pandas o polars, detectado automáticamente) como
    CSV/XLSX/Parquet a MinIO. Si el DataFrame está vacío, no hace nada.

    Args:
        s3_client: Cliente boto3 S3 (MinIO)
        df: DataFrame a subir (pandas.DataFrame o polars.DataFrame)
        bucket: Nombre del bucket
        key: Ruta del archivo dentro del bucket
        formato: "csv", "xlsx" o "parquet" (por defecto "csv"). "xlsx" con un
            DataFrame de polars requiere el paquete `xlsxwriter` (no instalado
            todavía) -- usa "csv" o "parquet" con polars hasta agregarlo.

    Returns:
        None
    """
    es_polars = isinstance(df, pl.DataFrame)
    vacio = df.is_empty() if es_polars else df.empty
    if vacio:
        print("⚠️  DataFrame vacío, no se sube")
        return

    local_file = f"/tmp/{os.path.basename(key)}"
    try:
        if es_polars:
            escritores = {"csv": df.write_csv, "parquet": df.write_parquet, "xlsx": df.write_excel}
        else:
            escritores = {
                "csv": lambda p: df.to_csv(p, index=False),
                "xlsx": lambda p: df.to_excel(p, index=False),
                "parquet": lambda p: df.to_parquet(p, index=False),
            }
        escritor = escritores.get(formato)
        if escritor is None:
            raise ValueError(f"Formato no soportado: {formato}")
        escritor(local_file)

        s3_client.upload_file(local_file, bucket, key)
        os.remove(local_file)
        print(f"✓ Subido a s3://{bucket}/{key} ({'polars' if es_polars else 'pandas'}): {len(df)} registros")
    except Exception as e:
        print(f"✗ Error subiendo a s3://{bucket}/{key}: {e}")
        raise
