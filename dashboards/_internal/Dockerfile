FROM python:3.11-slim
ENV TZ=America/Guayaquil
# TZ requiere la base de zonas horarias del sistema.
RUN apt-get update \
    && apt-get install -y --no-install-recommends tzdata \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
RUN pip install --no-cache-dir streamlit polars-lts-cpu duckdb plotly boto3 mlflow
EXPOSE 8501
CMD ["streamlit", "run", "app.py", "--server.address=0.0.0.0", "--server.port=8501"]
