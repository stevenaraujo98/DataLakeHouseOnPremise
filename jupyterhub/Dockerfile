FROM quay.io/jupyterhub/jupyterhub:4.0

RUN pip install --no-cache-dir \
    jupyterhub \
    jupyterlab \
    notebook \
    polars \
    duckdb \
    mlflow \
    boto3 \
    plotly \
    pandas \
    scikit-learn \
    prefect

COPY jupyterhub_config.py /srv/jupyterhub/jupyterhub_config.py

EXPOSE 8000

CMD ["jupyterhub", "-f", "/srv/jupyterhub/jupyterhub_config.py"]