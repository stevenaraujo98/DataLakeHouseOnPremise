FROM quay.io/jupyterhub/jupyterhub:4.0

# System libraries — bypass GPG date-check issues in Docker build environments
RUN apt-get update \
    -o Acquire::Check-Valid-Until=false \
    -o Acquire::Check-Date=false \
    && apt-get install -y --no-install-recommends \
    libgomp1 \
    libopenblas-base \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*RUN pip install --no-cache-dir \
    "jupyterhub==4.0.*" \
    jupyterlab \
    notebook \
    ipykernel \
    jupyterhub-nativeauthenticator \
    psycopg2-binary \
    polars-lts-cpu \
    duckdb \
    "mlflow>=2.10,<3" \
    boto3 \
    s3fs \
    plotly \
    pandas \
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