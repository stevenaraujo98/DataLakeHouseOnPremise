FROM quay.io/jupyterhub/jupyterhub:4.0

# System libraries required by numpy, scikit-learn, mlflow native extensions
RUN apt-get update && apt-get install -y --no-install-recommends \
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
    polars-lts-cpu \
    duckdb \
    "mlflow>=2.10,<3" \
    boto3 \
    s3fs \
    plotly \
    pandas \
    scikit-learn \
    prefect

# Register the kernel so Jupyter can find it
RUN python -m ipykernel install --sys-prefix

COPY jupyterhub_config.py /etc/jupyterhub/jupyterhub_config.py

EXPOSE 8000

CMD ["jupyterhub", "-f", "/etc/jupyterhub/jupyterhub_config.py"]