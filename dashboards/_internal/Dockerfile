FROM python:3.11-slim
WORKDIR /app
RUN pip install --no-cache-dir streamlit polars-lts-cpu duckdb plotly boto3 mlflow
EXPOSE 8501
CMD ["streamlit", "run", "app.py", "--server.address=0.0.0.0", "--server.port=8501"]