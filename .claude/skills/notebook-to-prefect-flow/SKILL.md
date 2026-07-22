---
name: notebook-to-prefect-flow
description: Converts a JupyterHub notebook (.ipynb) in this repo into a Prefect flow .py script that follows this project's house conventions (reusing flows/common_tasks.py, Spanish task names, the try/except/finally + emoji-status style, PYTHONPATH-based imports). Use this whenever the user asks to turn a notebook into a Prefect flow/job/script, wants to schedule or automate a notebook, says things like "convierte este notebook a un flow de prefect", "pasa este notebook a script py", "crea el flow para X.ipynb", "quiero programar este análisis", or points at a .ipynb file and asks to deploy/automate it — even if they don't say "Prefect" explicitly, since scheduling a notebook in this repo always means a Prefect flow.
---

# Notebook → Prefect flow

Turns a notebook into a `.py` Prefect flow that looks like it was written by
whoever wrote the rest of this repo's flows, not a generic Prefect tutorial
example. Read the four files below before writing anything — they are the
actual source of truth, and this skill intentionally doesn't restate their
content in full so it can't drift out of sync with them.

- [flows/common_tasks.py](../../flows/common_tasks.py) — reusable `@task`s
  for Postgres/MinIO (`connect_postgres`, `cerrar_conexion`, `leer_query`,
  `conectar_minio`, `descargar_csv_minio`, `subir_dataframe_csv`).
- [flows/analisis_chat_th.py](../../flows/analisis_chat_th.py) — the fullest
  real example of house style: `@task(name="...")` with Spanish names,
  `try/except` that re-raises as `RuntimeError`, `print()` status lines with
  ✓/✗/⚠️, one `@flow` orchestrating everything in `try/finally` (closing the
  DB connection in `finally`), and `if __name__ == "__main__":` for local
  testing.
- [PREFECT_JUPYTER_GUIDE.md](../../PREFECT_JUPYTER_GUIDE.md) — the full
  lifecycle: where the file goes, how it's tested (`python mi_flow.py` in a
  JupyterHub terminal), how it's deployed (`prefect deploy mi_flow.py:mi_flow
  --name "..." --pool default`), and why `from common_tasks import ...` just
  works without relative imports (`PYTHONPATH`).
- [AGENTS.md](../../AGENTS.md), section "Prefect flows: org / shared /
  users" — explains why shared code lives in the git repo (`flows/`) and
  per-user flows live next to the user's notebooks instead.

## Why reuse common_tasks.py instead of writing fresh connection code

Every flow in this repo eventually needs the same handful of things: a
Postgres connection, a MinIO client, a CSV round-trip through MinIO. If each
converted notebook reimplements that inline (like `analisis_chat_th.py`
does — it predates `common_tasks.py`), the project ends up with N slightly
different copies of the same connection logic, each one a separate thing to
fix if MinIO credentials or the Postgres host ever change. `common_tasks.py`
exists precisely so that doesn't happen. Treat it as the first place to
look, not an optional nicety.

## Steps

1. **Read the notebook.** Go through its cells in order — imports, any
   config/env-var reads, the actual data logic, and what it writes out at
   the end (a file, a table, an upload to MinIO). Note anything that looks
   notebook-only and should be dropped (progress bars, `display()`/plotting
   calls meant for interactive viewing, `%pip install` magics — those become
   Dockerfile/dependency concerns, not flow code, see step 6).

2. **Match logic to `common_tasks.py`.** For each piece of the notebook that
   connects to Postgres, runs a query, connects to MinIO, or uploads/
   downloads a CSV, check whether an existing task in `common_tasks.py`
   already does it. Import and call it — don't re-derive connection strings
   or re-instantiate `boto3.client(...)` inline. If the notebook reads a
   non-CSV format (Excel, Parquet, JSON) there may be no matching task yet;
   that's fine, write a local `@task` for it in the new flow file.

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
   house style from `analisis_chat_th.py`: Spanish `name=` on tasks, a
   `try/except` that raises `RuntimeError` with context on failure, status
   `print()`s with ✓ on success / ⚠️ on recoverable issues / ✗ on failure,
   and a `try/finally` in the flow that closes any DB connection
   unconditionally. End with `if __name__ == "__main__":` calling the flow,
   so it can be run directly for local testing per the guide.

5. **Save it next to the notebook, not in the repo's `flows/` folder.** The
   target path is the same directory as the source notebook (a per-user
   folder under `/home/{usuario}/{proyecto}/` on the server, i.e.
   `/data/datascience/notebooks/{usuario}/{proyecto}/` — see AGENTS.md's
   "Prefect flows" section). That's a per-user flow, distinct from the
   organizational flows tracked in this git repo's `flows/`. Only write into
   `flows/` if the user explicitly says this is meant to become a shared,
   team-maintained flow like `analisis_chat_th.py`. If the flow's name isn't
   obvious from the notebook's filename/content, ask the user what to call
   the file and the `@flow` function rather than guessing.

6. **After writing the file, don't try to test or deploy it yourself** —
   this skill runs wherever Claude currently is (which may not be the actual
   JupyterHub container/server), and `prefect deploy` from the wrong place
   is exactly the mistake `PREFECT_JUPYTER_GUIDE.md` warns about. Instead,
   point the user at the next steps from the guide: run `python mi_flow.py`
   in a JupyterHub terminal to test locally, then `prefect deploy
   mi_flow.py:mi_flow --name "..." --pool default` to register it, then
   schedule/run it per the guide's later sections. If the notebook imports a
   package that isn't in `prefect-worker/Dockerfile` yet, mention that too —
   it'll run fine via `python mi_flow.py` in JupyterHub but fail once
   deployed, per the guide's troubleshooting table.
