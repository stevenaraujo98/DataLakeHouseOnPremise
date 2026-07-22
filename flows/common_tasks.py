"""
Tareas compartidas de Prefect: conexión a PostgreSQL y MinIO (S3).
==================================================================

Vive en `flows/` (git, montado como /flows/org en prefect/prefect-worker
y /srv/flows/org en jupyterhub) porque es infraestructura reutilizada por
TODOS los flows del proyecto, no un experimento de un usuario.

Uso desde cualquier flow (org, shared o de un usuario en /flows/users):

    from common_tasks import connect_postgres, conectar_minio, leer_query, \
        descargar_csv_minio, subir_dataframe_csv

Esto funciona sin imports relativos porque /flows/org está en PYTHONPATH
(ver PYTHONPATH en docker-compose.yml y jupyterhub_config.py).
"""

import os

import boto3
import pandas as pd
import psycopg2
from prefect import task

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


@task(name="Descargar CSV desde MinIO")
def descargar_csv_minio(s3_client, bucket: str, key: str) -> pd.DataFrame:
    """Descargar un CSV de MinIO. Si no existe, devuelve un DataFrame vacío."""
    local_file = f"/tmp/{os.path.basename(key)}"
    try:
        s3_client.download_file(bucket, key, local_file)
        df = pd.read_csv(local_file)
        os.remove(local_file)
        print(f"✓ Descargado s3://{bucket}/{key}: {len(df)} registros")
        return df
    except s3_client.exceptions.NoSuchKey:
        print(f"⚠️  No existe s3://{bucket}/{key}, devolviendo DataFrame vacío")
        return pd.DataFrame()
    except Exception as e:
        print(f"⚠️  Error descargando s3://{bucket}/{key}: {e}, devolviendo DataFrame vacío")
        return pd.DataFrame()


@task(name="Subir DataFrame como CSV a MinIO")
def subir_dataframe_csv(s3_client, df: pd.DataFrame, bucket: str, key: str):
    if df.empty:
        print("⚠️  DataFrame vacío, no se sube")
        return
    local_file = f"/tmp/{os.path.basename(key)}"
    try:
        df.to_csv(local_file, index=False)
        s3_client.upload_file(local_file, bucket, key)
        os.remove(local_file)
        print(f"✓ Subido a s3://{bucket}/{key}: {len(df)} registros")
    except Exception as e:
        print(f"✗ Error subiendo a s3://{bucket}/{key}: {e}")
        raise
