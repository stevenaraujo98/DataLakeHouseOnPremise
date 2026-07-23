---
name: notebook-to-prefect-flow
description: Converts a JupyterHub notebook (.ipynb) in this repo into a Prefect flow .py script that follows this project's house conventions (reusing flows/common_tasks.py, cache_policy=NO_CACHE on I/O tasks, Spanish task names, the try/except/finally + emoji-status style, PYTHONPATH-based imports) and walks the user through deploying it correctly (right pool, right directory, right entrypoint name). Use this whenever the user asks to turn a notebook into a Prefect flow/job/script, wants to schedule or automate a notebook, says things like "convierte este notebook a un flow de prefect", "pasa este notebook a script py", "crea el flow para X.ipynb", "quiero programar este análisis", or points at a .ipynb file and asks to deploy/automate it — even if they don't say "Prefect" explicitly, since scheduling a notebook in this repo always means a Prefect flow.
---

# Notebook → Prefect flow

Turns a notebook into a `.py` Prefect flow that looks like it was written by
whoever wrote the rest of this repo's flows, not a generic Prefect tutorial
example — and gets the deploy right the first time, since several of the
conventions below exist specifically because the naive/tutorial way of doing
them broke in this project. Read the four files below before writing
anything — they are the actual source of truth, and this skill intentionally
doesn't restate their content in full so it can't drift out of sync with them.

- [flows/common_tasks.py](../../flows/common_tasks.py) — reusable `@task`s
  for Postgres/MinIO: `connect_postgres`, `cerrar_conexion`, `leer_query`,
  `conectar_minio`, `descargar_archivo_minio` (CSV/XLSX/Parquet, pandas or
  polars via `engine=`), `subir_dataframe_archivo` (same formats, detects
  pandas vs. polars automatically from the `df` you pass). All six are
  decorated `cache_policy=NO_CACHE` — see why below.
- [flows/analisis_chat_th.py](../../flows/analisis_chat_th.py) — the fullest
  real example of house style, and the one that's actually been deployed and
  run successfully: `@task(name="...")` with Spanish names, `cache_policy=
  NO_CACHE` on every task, `try/except` that re-raises as `RuntimeError`,
  status `print()`s with ✓/✗/⚠️, a module-level `MAX_RETRIES`/`RETRY_DELAY`
  pair applied via `.with_options(retries=..., retry_delay_seconds=...)`
  when calling the shared `common_tasks` functions, one `@flow` orchestrating
  everything in `try/finally` (closing the DB connection in `finally`, no
  `retries=` on the `@flow` itself — see why below), and
  `if __name__ == "__main__":` for local testing.
- [PREFECT_JUPYTER_GUIDE.md](../../PREFECT_JUPYTER_GUIDE.md) — the full
  lifecycle: where the file goes, how it's tested (`python mi_flow.py` in a
  JupyterHub terminal), the `/flows/...` vs. `/home`/`/srv/flows/...` deploy
  path gotcha (step 0/4), which of the 4 work pools to deploy to (step 5),
  the interactive prompts `prefect deploy` asks and how to answer them (step
  4), the cron timezone gotcha (step 7), and its Troubleshooting table —
  every row in that table is a real error this project hit.
- [AGENTS.md](../../AGENTS.md), sections "Prefect flows: org / shared /
  users" and "Prefect work pools" — why shared code lives in the git repo
  (`flows/`) and per-user flows live next to the user's notebooks instead,
  and the pool-per-workload-type reasoning.

## Why reuse common_tasks.py instead of writing fresh connection code

Every flow in this repo eventually needs the same handful of things: a
Postgres connection, a MinIO client, a file round-trip through MinIO. If each
converted notebook reimplements that inline (like `analisis_chat_th.py`
originally did, before it was refactored to import from `common_tasks.py`),
the project ends up with N slightly different copies of the same connection
logic, each one a separate thing to fix if MinIO credentials or the Postgres
host ever change. `common_tasks.py` exists precisely so that doesn't happen.
Treat it as the first place to look, not an optional nicety.

## Why every task needs `cache_policy=NO_CACHE`

Prefect 3 tries to cache each task's result by hashing its input arguments,
by default, even if you never asked for caching. The moment a task takes a
live DB connection, an S3/boto3 client, or sometimes even a DataFrame as an
argument, hashing fails and Prefect logs a scary-looking `HashError`/
`cannot pickle ...` traceback — **the task still runs and completes fine**,
this is only noise, but it clutters every single run's logs and looks like a
failure to anyone skimming them. Every task in this codebase does I/O
(DB reads, uploads, API calls) — none of them are pure functions where
input-based caching would ever help anyway. So: add `cache_policy=NO_CACHE`
(`from prefect.cache_policies import NO_CACHE`) to **every** `@task(...)`
you write, not just the ones that obviously take a connection/client. Don't
skip this to save a line — it's exactly the kind of thing that's easy to
forget on a first pass and only shows up as confusing log noise later.

## Steps

1. **Read the notebook.** Go through its cells in order — imports, any
   config/env-var reads, the actual data logic, and what it writes out at
   the end (a file, a table, an upload to MinIO). Note anything that looks
   notebook-only and should be dropped (progress bars, `display()`/plotting
   calls meant for interactive viewing, `%pip install` magics — those become
   Dockerfile/dependency concerns, not flow code, see step 8).

2. **Match logic to `common_tasks.py`.** For each piece of the notebook that
   connects to Postgres, runs a query, connects to MinIO, or uploads/
   downloads a file, check whether an existing task in `common_tasks.py`
   already does it — `descargar_archivo_minio`/`subir_dataframe_archivo`
   cover CSV, XLSX, and Parquet already, and pandas or polars (pass
   `engine="polars"` to the download, or just pass a polars DataFrame to the
   upload — it's auto-detected). Import and call these — don't re-derive
   connection strings or re-instantiate `boto3.client(...)` inline. If the
   notebook needs a format these don't cover, write a local `@task` for it
   (with `cache_policy=NO_CACHE`, same as everything else).

3. **Flag genuinely new reusable patterns, don't silently duplicate them.**
   If the notebook does something that isn't in `common_tasks.py` yet but
   looks like it'll come up again in other flows (e.g. a second table this
   team queries often, a specific MinIO bucket/prefix convention), say so to
   the user as a suggestion to add it to `common_tasks.py` later. Don't add
   it there yourself without asking — `common_tasks.py` is shared
   organizational code, not a place to unilaterally drop something for one
   flow's convenience.

4. **Write the tasks and the flow.** Wrap the remaining transformation
   logic (the parts genuinely specific to this notebook) into `@task`
   functions, and one `@flow` function that calls them in order. Match the
   house style from `analisis_chat_th.py`: Spanish `name=` on tasks,
   `cache_policy=NO_CACHE` on every task (see above), a `try/except` that
   raises `RuntimeError` with context on failure, status `print()`s with ✓ on
   success / ⚠️ on recoverable issues / ✗ on failure, and a `try/finally` in
   the flow that closes any DB connection unconditionally. End with
   `if __name__ == "__main__":` calling the flow, so it can be run directly
   for local testing per the guide.

5. **If the notebook does anything worth retrying automatically** (a
   flaky external call — Postgres, MinIO, OpenAI, any network I/O), don't
   add `retries=` to `common_tasks.py`'s functions themselves (they're
   shared infra, not every caller wants the same retry policy). Instead,
   define `MAX_RETRIES`/`RETRY_DELAY` constants at the top of the new flow
   file and apply them per-call with `.with_options(retries=MAX_RETRIES,
   retry_delay_seconds=RETRY_DELAY)`, e.g.
   `connect_postgres.with_options(retries=MAX_RETRIES, retry_delay_seconds=RETRY_DELAY)(database=...)`
   — see `analisis_chat_th.py` for the real pattern. Don't put `retries=` on
   the `@flow` itself: since every I/O task already retries individually, a
   flow-level retry would re-run the *entire* flow from scratch after a late
   failure, silently re-paying for anything already done once (e.g.
   re-classifying messages with OpenAI a second time).

6. **Save it next to the notebook, not in the repo's `flows/` folder.** The
   target path is the same directory as the source notebook (a per-user
   folder under `/home/{usuario}/{proyecto}/` on the server, i.e.
   `/data/datascience/notebooks/{usuario}/{proyecto}/` — see AGENTS.md's
   "Prefect flows" section). That's a per-user flow, distinct from the
   organizational flows tracked in this git repo's `flows/`. Only write into
   `flows/` if the user explicitly says this is meant to become a shared,
   team-maintained flow like `analisis_chat_th.py`. If the flow's name isn't
   obvious from the notebook's filename/content, ask the user what to call
   the file and the `@flow` function rather than guessing.

7. **If the notebook reads an env var like an API key, check whether a
   project-scoped one already exists** (e.g. `OPENAI_API_KEY_TH` for
   OpenAI calls tied to the TH project) before inventing a generic new name
   — look at `.env.example` and how `analisis_chat_th.py` resolves
   `OPENAI_API_KEY` (checks the project-scoped name first, then generic
   fallbacks). If a genuinely new secret is needed, mention that it needs to
   be added to `.env` — `jupyterhub` and every `prefect-worker-*` already
   pick up anything in `.env` automatically (`env_file:` in
   `docker-compose.yml`), but reaching individual user notebooks additionally
   requires its name to match a known prefix in `c.Spawner.environment`
   (`jupyterhub/jupyterhub_config.py`) — don't try to edit that yourself,
   flag it to the user.

8. **After writing the file, don't try to test or deploy it yourself** —
   this skill runs wherever Claude currently is (which may not be the actual
   JupyterHub container/server). Instead, give the user the exact next
   commands, matching what actually works in this project (not the generic
   Prefect tutorial flow):
   - Test locally: `python mi_flow.py` in a JupyterHub terminal, from
     wherever the file actually is (`/home/{usuario}/{proyecto}`, or the
     `/flows/users/...` mirror — either works for local testing since it
     doesn't touch a worker).
   - Deploy: first `cd` into the **`/flows/...` mirror path**, not
     `/home/...` or `/srv/flows/...` — `cd /flows/users/{usuario}/{proyecto}`
     for a personal flow, `cd /flows/org` for an organizational one. This
     matters even though it's the same files: `prefect deploy` with local
     storage records the directory you ran it from, and that path has to
     exist inside the `prefect-worker-*` container that later executes the
     flow, or the run fails at execution time even though the deployment
     looked like it created fine. Then:
     `prefect deploy mi_flow.py:mi_flow --name "..." --pool <pool>` — the
     part after the colon **must be the real Python function name** of the
     `@flow`, not the file name and not the flow's `name="..."` display
     string, or it fails with `MissingFlowError` (which does tell you the
     right name).
   - Pick `<pool>` from the 4 that exist — `chats`, `training`,
     `dashboards`, or `default` if it's not clearly one of those yet (see
     AGENTS.md's "Prefect work pools" table). Don't invent a new pool name;
     it won't have a worker and the run will hang in `Scheduled` forever.
   - When `prefect deploy` asks "Would you like your workers to pull your
     flow code from a remote storage location...?", the answer is **`n`** —
     the code is already local to the workers via the shared mounts, and the
     image doesn't have `git` installed for the remote-storage path anyway.
   - If the notebook imports a package that isn't in
     `prefect-worker/Dockerfile` yet, mention that too — it'll run fine via
     `python mi_flow.py` in JupyterHub but fail once deployed, per the
     guide's troubleshooting table.
