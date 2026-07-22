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
- Prefect uses PostgreSQL for API/server state. The `prefect` service is only the server (API + UI); it does not execute flow code.
- `prefect-worker-chats`, `prefect-worker-training`, `prefect-worker-dashboards` are three separate services, all built from `./prefect-worker`, that actually execute deployed flows — one per work pool, grouped by workload type (not by project/unit). Without the matching worker running, a deployment's runs stay `Scheduled`/`Late` forever. See "Prefect work pools" below.
- JupyterHub provides notebook access for users and mounts user homes from `/data/datascience/notebooks`.
- Streamlit serves dashboards from `dashboards/app.py` and reads data from MinIO.
- `minio-setup` is a one-shot bootstrap container that creates buckets and can be safely recreated.

## MinIO buckets explained
MinIO provides S3-compatible object storage with four automatically created buckets:

- **`raw-data`** — Stores unprocessed source data (CSV, JSON, etc.). Suggested path structure: `s3://raw-data/bronze/date/batch/data.csv`. Used as the single source of truth for ingested external data; consumed by JupyterHub, Prefect, and Streamlit.

- **`processed-data`** — Stores transformed and refined data in multiple layers:
  - `silver/`: cleaned and enriched data
  - `gold/`: aggregated data ready for consumption
  - `features/`: engineered features for ML models (e.g., `customer_features/v2026_03_13/`)
  - Intermediate storage between raw ingestion and final consumption; consumed for analysis, dashboards, and model training.

- **`models`** — Stores serialized machine learning models (pickle, joblib, ONNX, etc.). Provides manual versioning and management of trained models independent of MLflow's artifact system.

- **`artifacts`** — Managed automatically by MLflow (`--default-artifact-root s3://artifacts/`). Stores complete model artifacts, metrics, parameters, and experiment metadata with full MLflow integration and lifecycle tracking. Accessible via MLflow UI at `http://SERVER_IP:5000`.

All buckets are created automatically on first stack startup by the `minio-setup` bootstrap service.

## Prefect flows: org / shared / users
Prefect (`prefect` server, `prefect-worker`, `jupyterhub`) mounts three separate flow locations, each for a different purpose:

- **`/flows/org`** (`/srv/flows/org` in JupyterHub) → bind-mounted from `./flows` (this git repo). Organizational/template flows, e.g. `flows/analisis_chat_th.py`. Edited via git, not from inside a container.
- **`/flows/shared`** (`/srv/flows/shared` in JupyterHub) → bind-mounted from `/data/datascience/flows`. Reusable tasks/utilities imported by multiple users' flows (e.g. `common_tasks.py`).
- **`/flows/users`** (JupyterHub sees the same data as `/home`, since both come from `/data/datascience/notebooks`) → each user's per-user flow files live next to their notebooks, e.g. `/data/datascience/notebooks/{username}/{project}/prefect_flow.py`.

Correct workflow:
1. Users develop and test notebooks in JupyterHub under `/home/{username}/...`.
2. They convert working code into a `@flow`/`@task` Python file in the same folder.
3. **Deploy from a JupyterHub terminal** (`prefect deploy my_flow.py:my_flow --name "..." --pool <pool>`) — not from `docker exec -it ds_prefect`. The `prefect` service image is a bare server image without `pandas`/`boto3`/`psycopg2`/`torch`/etc., and it has no `PREFECT_API_URL` set, so a CLI `prefect deploy` run there either fails to import the flow or silently registers against an ephemeral local API instead of the real server. JupyterHub already has both the flow dependencies (see `jupyterhub/Dockerfile`) and `PREFECT_API_URL=http://prefect:4200/api` wired via `c.Spawner.environment`.
4. Create/manage the schedule from the Prefect UI (`http://SERVER_IP:4200`) or CLI.
5. The matching worker for `<pool>` (see "Prefect work pools" below) is what actually picks up and executes scheduled/triggered runs. If it is down, runs stay `Scheduled`/`Late` indefinitely — check `docker compose ps` and `docker exec -it ds_prefect prefect work-pool ls` when jobs don't run.

## Prefect work pools
Three work pools/workers exist, grouped by **workload type**, not by project or organizational unit — a concurrency limit is a resource control, and projects of the same type share a resource profile even across different units (e.g. TH chat analysis and academic chat analysis are both light DB+OpenAI calls; academic-risk-model training and career-planning-model training are both heavy CPU/RAM):

| Pool | Worker service | `--concurrency-limit` | For |
|---|---|---|---|
| `chats` | `prefect-worker-chats` | 3 | n8n chat analysis per unit (TH, académico, bienestar, ...) — light DB read + sentiment model + OpenAI classification |
| `training` | `prefect-worker-training` | 1 | Model training (riesgo académico, planificación académica, ODS, carreras, ...) — heaviest CPU/RAM; deliberately serialized so two trainings never compete for memory on the same host |
| `dashboards` | `prefect-worker-dashboards` | 20 | Data processing feeding dashboards — many, lighter ETL-style jobs |
| `default` | `prefect-worker-default` | 2 | Catch-all for whatever doesn't yet clearly fit the three above (one-off tests, a new flow while its real type is still being decided). Deliberately low concurrency since its workload shape is unknown by definition. |

Pick the pool by workload type at deploy time (`--pool chats`/`training`/`dashboards`/`default`); distinguish projects/units within a pool with `--tag` (e.g. `--tag th`, `--tag academico`) instead of creating a new pool per unit — that keeps the number of worker containers bounded as new projects get added. If something recurring ends up parked in `default`, migrate it to its proper typed pool rather than leaving it there long-term. If a workload doesn't fit any of the four, decide deliberately before adding another pool+worker (copy the `x-prefect-worker-common` anchor block in `docker-compose.yml`) — don't default to an existing pool just because it's there. Changing an existing pool's concurrency limit requires `prefect work-pool update <pool> --concurrency-limit N` — the `prefect work-pool create ... || true` in each worker's `command` is idempotent-safe but does not update an already-existing pool.

Shared task code: [flows/common_tasks.py](flows/common_tasks.py) holds reusable Postgres/MinIO tasks (`connect_postgres`, `conectar_minio`, `leer_query`, `subir_dataframe_csv`, ...). It lives in `flows/` (git) rather than `/data/datascience/flows` because it's infrastructure code shared by every flow, not a one-off script — treat it like real code (reviewed, versioned). Any flow (org, shared, or per-user) imports it directly with `from common_tasks import ...`; this works because `PYTHONPATH` includes `/flows/org:/flows/shared` (`prefect-worker` in `docker-compose.yml`) / `/srv/flows/org:/srv/flows/shared` (`jupyterhub_config.py` → `c.Spawner.environment`), so no relative-import gymnastics are needed regardless of where the calling flow lives.

Full step-by-step (notebook → flow → deploy → schedule → run-now → pause) is in [PREFECT_JUPYTER_GUIDE.md](PREFECT_JUPYTER_GUIDE.md).

## Important paths
- `docker-compose.yml`: source of truth for services, ports, dependencies and bind mounts.
- `sql/init-db.sql`: initial bootstrap for PostgreSQL databases. It only runs on first initialization of an empty Postgres data directory.
- `jupyterhub/jupyterhub_config.py`: JupyterHub authentication, spawner and persistence settings.
- `jupyterhub/Dockerfile`: JupyterHub image with Python/data tooling.
- `mlflow/Dockerfile`: MLflow server image.
- `prefect-worker/Dockerfile`: shared build for all three Prefect worker services (`prefect-worker-chats`/`-training`/`-dashboards`, see "Prefect work pools" above) — one image, one build context, reused via the `x-prefect-worker-common` YAML anchor in `docker-compose.yml`. Installs the data/ML subset of `jupyterhub/Dockerfile` (`pandas`, `boto3`, `psycopg2-binary`, `openai`, `s3fs`, `scikit-learn`, `duckdb`, `polars-lts-cpu`, `mlflow`, `torch`, `transformers`, ...) so flows converted from notebooks are likely to just work — deliberately excludes Jupyter/Streamlit-only packages (`jupyterhub`, `jupyterlab`, `notebook`, `ipykernel`, `jupyterhub-nativeauthenticator`, `streamlit`), which a headless worker never needs. If a flow needs a library that's in `jupyterhub/Dockerfile` but missing here, add it here too — it benefits all three workers at once.
- `flows/`: organizational flows tracked in git (mounted as `/flows/org` in `prefect`/`prefect-worker`, `/srv/flows/org` in `jupyterhub`), including the shared [flows/common_tasks.py](flows/common_tasks.py).
- `pgbouncer/pgbouncer.ini`, `pgbouncer/generate-config.sh`: reference PgBouncer config. Not currently mounted by the `pgbouncer` service in `docker-compose.yml` (it's configured purely via env vars) — keep this in mind before assuming a change here has any runtime effect.
- `diagrams/`: architecture diagram sources (`mermaid.txt`, `dbdiagram.txt`), documentation only, not used by any container.
- `dashboards/app.py`: Streamlit entrypoint.
- `ADITONAL.md`: operational notes and troubleshooting commands.
- `PREFECT_JUPYTER_GUIDE.md`: end-user runbook for going notebook → flow → deployment → schedule from JupyterHub.
- `MLFLOW_GUIDE.md`: end-user runbook for tracking experiments and logging/loading models from JupyterHub, Prefect flows, and from a machine outside the server.

## Persistence model
- Postgres data lives in `/data/datascience/postgres`.
- MinIO objects live in `/data/datascience/minio`.
- Prefect local state lives in `/data/datascience/prefect`.
- Organizational/shared/user flow code is not separately "owned" by Prefect: `/flows/org` comes from the git repo (`./flows`), `/flows/shared` from `/data/datascience/flows`, `/flows/users` from `/data/datascience/notebooks` (see "Prefect flows" section above). `prefect-worker` is stateless — it has no dedicated persistence directory, it only reads these flow mounts.
- JupyterHub cookie secret and local files live in `/data/datascience/jupyterhub`.
- User notebooks and home directories live in `/data/datascience/notebooks`.
- JupyterHub is configured to persist hub state in PostgreSQL database `jupyterhub`; legacy SQLite files may still exist in `/srv/jupyterhub` from older runs.

## Service relationships
- `mlflow` depends on healthy `postgres` and healthy `minio`.
- `prefect` depends on healthy `postgres`.
- `prefect-worker-chats`, `prefect-worker-training`, `prefect-worker-dashboards`, `prefect-worker-default` each depend on healthy `prefect` and started `mlflow`.
- `jupyterhub` depends on healthy `postgres` and started `mlflow`.
- `streamlit` depends on `minio` and `mlflow`.

## Dev environment tips
- Start from the repository root when running Docker Compose commands.
- Check `.env` before running the stack (see `.env.example`); the required variables are `POSTGRES_USER`, `POSTGRES_PASSWORD`, `MINIO_ROOT_USER`, `MINIO_ROOT_PASSWORD`, `JUPYTERHUB_ADMIN`, and `SERVER_IP`. `OPENAI_API_KEY_TH` is optional — flows that use it (e.g. `flows/analisis_chat_th.py`) degrade gracefully and skip the OpenAI-dependent step when it's unset.
- `jupyterhub` and `prefect-worker` use `env_file: .env`, so any variable added to `.env` automatically becomes available in those two containers — no `docker-compose.yml` edit needed for that first hop. The second hop (Hub container → each user's spawned single-user process) is separate: `c.Spawner.environment` in `jupyterhub/jupyterhub_config.py` only forwards variables whose name starts with a known credential prefix (`POSTGRES_`, `MINIO_`, `AWS_`, `MLFLOW_`, `PREFECT_`, `OPENAI_`, `OPEN_API_`, `SERVER_IP`) — deliberately not a full `os.environ` passthrough, to avoid leaking JupyterHub's own internal secrets (API token, cookie secret) into every user's notebook. A new `.env` var only reaches user notebooks automatically if its name matches one of those prefixes; otherwise add the prefix (or the exact name) to the tuple in `jupyterhub_config.py`. `prefect` (the server) and `postgres`/`minio` do not use `env_file` — they keep their required vars explicit with `${VAR:?...}` validation, which `env_file` would silently skip.
- `TZ=America/Guayaquil` alone does not change `datetime.now()` inside a container unless the `tzdata` package is installed in that image (see `jupyterhub/Dockerfile`, `prefect-worker/Dockerfile`). Separately, Prefect cron schedules default to UTC unless a `timezone` is set explicitly when creating the schedule — the container's `TZ` has no effect on when a schedule fires (see [PREFECT_JUPYTER_GUIDE.md](PREFECT_JUPYTER_GUIDE.md), step 6).
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
- For `prefect-worker/Dockerfile` changes, rebuild all four with `docker compose build prefect-worker-chats prefect-worker-training prefect-worker-dashboards prefect-worker-default` (they share one build), then confirm each appears as a subscribed worker via `docker exec -it ds_prefect prefect work-pool ls` and that a manually triggered flow run in the relevant pool actually transitions out of `Scheduled`/`Pending`.
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