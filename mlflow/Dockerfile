FROM python:3.11-slim

RUN pip install --no-cache-dir \
    mlflow==2.9.2 \
    psycopg2-binary \
    boto3 \
    pymysql

EXPOSE 5000

CMD ["mlflow", "server", \
     "--host", "0.0.0.0", \
     "--port", "5000", \
     "--backend-store-uri", "postgresql://postgres:postgres123@postgres:5432/mlflow", \
     "--default-artifact-root", "s3://artifacts/", \
     "--serve-artifacts"]
