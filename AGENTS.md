# AGENTS.md

## Project overview
- This repository defines a complete on-prem data platform orchestrated with Docker Compose.
- The stack combines PostgreSQL, MinIO, MLflow, Prefect, JupyterHub and Streamlit.
- The intended host is Linux or WSL-like environments because persistent bind mounts use absolute paths under `/data/datascience`.
- Persistence is host-based, not Docker-volume-based: deleting containers usually does not delete data, but deleting `/data/datascience/*` does.

## Architecture summary
- PostgreSQL stores relational metadata for MLflow, Prefect and JupyterHub.
- MinIO stores object data and MLflow artifacts in S3-compatible buckets.
- MLflow uses PostgreSQL for backend metadata and MinIO bucket `artifacts` for artifacts.
- Prefect uses PostgreSQL for API/server state and mounts `./flows` into the container.
- JupyterHub provides notebook access for users and mounts user homes from `/data/datascience/notebooks`.
- Streamlit serves dashboards from `dashboards/app.py` and reads data from MinIO.
- `minio-setup` is a one-shot bootstrap container that creates buckets and can be safely recreated.

## Important paths
- `docker-compose.yml`: source of truth for services, ports, dependencies and bind mounts.
- `init-db.sql`: initial bootstrap for PostgreSQL databases. It only runs on first initialization of an empty Postgres data directory.
- `jupyterhub/jupyterhub_config.py`: JupyterHub authentication, spawner and persistence settings.
- `jupyterhub/Dockerfile`: JupyterHub image with Python/data tooling.
- `mlflow/Dockerfile`: MLflow server image.
- `dashboards/app.py`: Streamlit entrypoint.
- `ADITONAL.md`: operational notes and troubleshooting commands.

## Persistence model
- Postgres data lives in `/data/datascience/postgres`.
- MinIO objects live in `/data/datascience/minio`.
- Prefect local state lives in `/data/datascience/prefect`.
- JupyterHub cookie secret and local files live in `/data/datascience/jupyterhub`.
- User notebooks and home directories live in `/data/datascience/notebooks`.
- JupyterHub is configured to persist hub state in PostgreSQL database `jupyterhub`; legacy SQLite files may still exist in `/srv/jupyterhub` from older runs.

## Service relationships
- `mlflow` depends on healthy `postgres` and healthy `minio`.
- `prefect` depends on healthy `postgres`.
- `jupyterhub` depends on healthy `postgres` and started `mlflow`.
- `streamlit` depends on `minio` and `mlflow`.

## Dev environment tips
- Start from the repository root when running Docker Compose commands.
- Check `.env` before running the stack; the required variables are `POSTGRES_USER`, `POSTGRES_PASSWORD`, `MINIO_ROOT_USER`, `MINIO_ROOT_PASSWORD`, `JUPYTERHUB_ADMIN`, and `SERVER_IP`.
- Create host persistence directories before first boot if they do not exist under `/data/datascience`.
- Prefer `docker compose up -d service_name` or `docker compose restart service_name` for targeted work instead of restarting the full stack.
- If you change `docker-compose.yml`, validate it with `docker compose config` before restarting services.
- If you change a Dockerfile, rebuild only the affected service with `docker compose build service_name`.

## Inspection commands
- List services: `docker compose ps`
- Follow logs: `docker compose logs -f` or `docker compose logs -f service_name`
- Enter a container shell: `docker exec -it <container_name> bash` or `sh`
- Inspect mounts and env: `docker inspect <container_name>`
- Inspect PostgreSQL databases: `docker exec -it ds_postgres psql -U "$POSTGRES_USER" -d postgres`
- Inspect MinIO files: `docker exec -it ds_minio sh` then `ls -lah /data`

## Testing instructions
- There is no automated unit/integration test suite in this repository today.
- Validate infrastructure changes with `docker compose config`.
- After changing Dockerfiles or runtime configuration, rebuild and restart only affected services.
- For JupyterHub changes, check startup logs and confirm tables exist in database `jupyterhub`.
- For MLflow changes, confirm the UI loads and artifact logging still writes to MinIO.
- For Prefect changes, confirm `http://SERVER_IP:4200/api` responds and the server starts cleanly.
- For Streamlit changes, confirm `http://SERVER_IP:8501` loads without runtime errors.

## Data safety rules
- Safe: `docker compose restart service_name`
- Safe: `docker compose down` followed by `docker compose up -d`
- Usually safe: deleting and recreating an individual container while keeping host bind mounts intact
- Destructive: deleting anything under `/data/datascience/postgres`, `/data/datascience/minio`, `/data/datascience/prefect`, `/data/datascience/jupyterhub`, or `/data/datascience/notebooks`
- `docker compose down -v` is less relevant here because the main persistence uses bind mounts rather than named Docker volumes

## JupyterHub notes
- Authentication uses `nativeauthenticator`.
- Users can sign up through `/hub/signup` when signup is enabled.
- User home directories are created under `/home/{username}` and persisted via host bind mount.
- Hub metadata now targets PostgreSQL through `JUPYTERHUB_DB_URL`.
- If old SQLite-based users must be preserved, plan a deliberate migration instead of deleting the old file immediately.

## PR instructions
- Keep changes minimal and focused on the service being modified.
- Do not replace bind mounts with named volumes unless the operational model is intentionally changing.
- Preserve service names and published ports unless there is an explicit reason to change them.
- Document any persistence-impacting change in `README.md` or `ADITONAL.md`.
- Before finishing, verify the changed files are syntactically valid and note any runtime checks you could not execute.