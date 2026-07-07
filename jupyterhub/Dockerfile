FROM quay.io/jupyterhub/jupyterhub:4.0

# All packages are pre-built binary wheels — no system compiler needed
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
    boto3 \
    s3fs \
    plotly \
    pandas \
    scikit-learn \
    prefect \
    streamlit

# PyTorch CPU-only (pre-built wheel, no gcc needed) + HuggingFace stack
RUN pip install --no-cache-dir \
    --extra-index-url https://download.pytorch.org/whl/cpu \
    torch

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