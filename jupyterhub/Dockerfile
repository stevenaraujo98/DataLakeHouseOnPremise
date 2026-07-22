FROM quay.io/jupyterhub/jupyterhub:4.0

# Necesario para que TZ=America/Guayaquil (docker-compose.yml) realmente
# cambie datetime.now(): sin el paquete tzdata, glibc no encuentra la zona
# y todo corre en UTC aunque la env var esté seteada.
ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=America/Guayaquil

# System libraries required by numpy, scikit-learn, mlflow native extensions
RUN apt-get update && apt-get install -y --no-install-recommends \
    tzdata \
    libgomp1 \
    libopenblas-base \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
    "jupyterhub==4.0.*" \
    jupyterlab \
    notebook \
    ipykernel \
    jupyterhub-nativeauthenticator \
    psycopg2-binary \
    polars-lts-cpu \
    duckdb \
    "mlflow>=2.10,<3" \
    "boto3>=1.42.90,<1.43.0" \
    s3fs \
    plotly \
    pandas \
    openpyxl \
    openai \
    scikit-learn \
    prefect \
    streamlit

# PyTorch CPU-only + HuggingFace stack for model inference (no GPU needed)
RUN pip install --no-cache-dir \
    torch --index-url https://download.pytorch.org/whl/cpu

RUN pip install --no-cache-dir \
    transformers \
    accelerate \
    sentencepiece \
    tokenizers

# Register the kernel so Jupyter can find it
RUN python -m ipykernel install --sys-prefix

COPY jupyterhub_config.py /etc/jupyterhub/jupyterhub_config.py

EXPOSE 8000

CMD ["jupyterhub", "-f", "/etc/jupyterhub/jupyterhub_config.py"]