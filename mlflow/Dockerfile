FROM python:3.11-slim

RUN pip install --no-cache-dir \
    "mlflow>=2.10,<3" \
    psycopg2-binary \
    boto3 \
    pymysql

EXPOSE 5000

ENV MLFLOW_DEFAULT_ARTIFACT_ROOT=s3://artifacts/

CMD ["sh", "-c", "mlflow server \
     --host 0.0.0.0 \
     --port 5000 \
     --backend-store-uri $MLFLOW_BACKEND_STORE_URI \
     --default-artifact-root $MLFLOW_DEFAULT_ARTIFACT_ROOT \
     --serve-artifacts"]
