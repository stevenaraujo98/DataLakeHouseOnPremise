FROM prefecthq/prefect:3-latest

# Necesario para que TZ=America/Guayaquil (docker-compose.yml) realmente
# cambie datetime.now() dentro de los flows (ej. el timestamp del Excel en
# analisis_chat_th.py): sin tzdata, glibc no encuentra la zona y corre en UTC.
ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=America/Guayaquil

# Mismas libs de sistema que jupyterhub/Dockerfile (numpy, scikit-learn,
# mlflow, duckdb usan extensiones nativas).
RUN apt-get update && apt-get install -y --no-install-recommends \
    tzdata \
    libgomp1 \
    libopenblas-base \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Subconjunto de datos/ML de jupyterhub/Dockerfile que los flows pueden
# necesitar en runtime. NO se instala todo lo de jupyterhub/Dockerfile:
# jupyterhub, jupyterlab, notebook, ipykernel, jupyterhub-nativeauthenticator
# y streamlit son específicos del servidor de notebooks/dashboard y no
# los usa un worker headless.
# Si un flow convertido desde un notebook necesita otra librería que el
# notebook sí tenía, agrégala aquí también.
RUN pip install --no-cache-dir \
    pandas \
    "boto3>=1.42.90,<1.43.0" \
    psycopg2-binary \
    python-dotenv \
    openai \
    openpyxl \
    s3fs \
    scikit-learn \
    polars-lts-cpu \
    duckdb \
    "mlflow>=2.10,<3"

# PyTorch CPU-only + HuggingFace stack (mismo patrón que jupyterhub/Dockerfile)
RUN pip install --no-cache-dir \
    torch --index-url https://download.pytorch.org/whl/cpu

RUN pip install --no-cache-dir \
    transformers \
    accelerate \
    sentencepiece \
    tokenizers
