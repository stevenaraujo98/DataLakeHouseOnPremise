# Guía: uso de MLflow (JupyterHub, Prefect y acceso externo)

Cómo trackear experimentos, subir (log) modelos, controlarlos vía UI/API, y
cargarlos de vuelta — tanto desde JupyterHub, desde flows de Prefect, como
desde una máquina fuera del servidor donde está desplegado el stack.

Contexto (ver también [AGENTS.md](AGENTS.md)):
- `mlflow` ([docker-compose.yml](docker-compose.yml)) usa PostgreSQL (base
  `mlflow`, vía `pgbouncer`) como *backend store* (experimentos, runs,
  params, métricas) y el bucket `s3://artifacts/` en MinIO como
  *artifact store* (modelos, archivos, plots).
- La UI/API queda en el puerto **5000** del contenedor `ds_mlflow`.
- El bucket `artifacts` es gestionado por MLflow, no lo toques a mano — ver
  la sección "MinIO buckets" en AGENTS.md.

---

## 0. Quién ya tiene las variables configuradas

| Servicio | `MLFLOW_TRACKING_URI` | `MLFLOW_S3_ENDPOINT_URL` | Credenciales S3 |
|---|---|---|---|
| `jupyterhub` (y notebooks de usuario) | `http://mlflow:5000` | `http://minio:9000` | `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` = `MINIO_ROOT_USER`/`PASSWORD` |
| `prefect-worker` | `http://mlflow:5000` | `http://minio:9000` | ídem |
| `streamlit` | `http://mlflow:5000` | (no serializa modelos, solo lee) | ídem |

Todo esto ya viene inyectado por `docker-compose.yml` — dentro de un
notebook de JupyterHub o de un flow de Prefect **no hace falta** llamar a
`mlflow.set_tracking_uri(...)`, MLflow lo toma solo de la variable de
entorno.

> Si acabas de agregar las variables de `prefect-worker` al
> `docker-compose.yml`, recuerda recrear el contenedor en el servidor para
> que tomen efecto (ver sección 6.4, "Aplicar cambios en el servidor").

---

## 1. Uso desde JupyterHub

```python
import mlflow

mlflow.set_experiment("mi-proyecto")   # se crea si no existe

with mlflow.start_run(run_name="baseline"):
    mlflow.log_param("modelo", "RandomForest")
    mlflow.log_param("n_estimators", 200)

    # ... entrenar ...

    mlflow.log_metric("rmse", 0.234)
    mlflow.log_metric("r2", 0.81)

    # Sube el modelo completo (pickle + metadata + conda/requirements) a
    # s3://artifacts/<experiment_id>/<run_id>/artifacts/model
    mlflow.sklearn.log_model(modelo, "model")
```

Reemplaza `mlflow.sklearn` por el flavor que corresponda: `mlflow.xgboost`,
`mlflow.pytorch`, `mlflow.statsmodels`, etc. Para un objeto arbitrario que no
tenga flavor propio, usa `mlflow.pyfunc.log_model` o sube el archivo suelto
con `mlflow.log_artifact("modelo.pkl")`.

Revisa el resultado en `http://SERVER_IP:5000`.

---

## 2. Uso desde flows de Prefect

Igual que en JupyterHub, mismo `MLFLOW_TRACKING_URI` (ya inyectado en
`prefect-worker`). Patrón recomendado: una `@task` de entrenamiento que loguea
dentro de su propio `with mlflow.start_run()`, llamada desde el `@flow`:

```python
from prefect import flow, task
import mlflow
from common_tasks import connect_postgres, cerrar_conexion, leer_query

@task(name="Entrenar y loguear a MLflow")
def entrenar_y_loguear(df):
    mlflow.set_experiment("mi-proyecto")
    with mlflow.start_run(run_name="prefect-run"):
        X, y = df.drop(columns=["target"]), df["target"]
        modelo = entrenar(X, y)  # tu función

        mlflow.log_param("n_estimators", 200)
        mlflow.log_metric("rmse", evaluar(modelo, X, y))
        mlflow.sklearn.log_model(modelo, "model")

        return mlflow.active_run().info.run_id

@flow(name="entrenamiento-mensual")
def entrenamiento_mensual():
    conexion = connect_postgres(database="saacdata")
    try:
        df = leer_query(conexion, "SELECT * FROM mi_tabla")
        run_id = entrenar_y_loguear(df)
        print(f"✓ Run registrado: {run_id}")
    finally:
        cerrar_conexion(conexion)

if __name__ == "__main__":
    entrenamiento_mensual()
```

Para probar, deployar y programar este flow, sigue el flujo normal descrito
en [PREFECT_JUPYTER_GUIDE.md](PREFECT_JUPYTER_GUIDE.md) (todo se hace desde
una terminal de JupyterHub).

> `prefect-worker/Dockerfile` ya incluye `mlflow` — si un flow importa un
> flavor de un framework que no está instalado ahí (ej. `mlflow.pytorch`
> necesita `torch`, que sí está; pero librerías nuevas que agregues no lo
> estarán), agrégalo a `prefect-worker/Dockerfile` y reconstruye ese
> servicio.

---

## 3. Controlar experimentos y runs

**Desde la UI** (`http://SERVER_IP:5000`):
- Comparar runs: selecciona varios en la tabla del experimento → **Compare**.
- Buscar por parámetro/métrica: barra de búsqueda con sintaxis tipo
  `metrics.rmse < 0.3 and params.n_estimators = "200"`.
- Ver artefactos de un run (incluye el modelo serializado) en la pestaña
  **Artifacts** del run.

**Desde código** (útil dentro de un flow o notebook para decidir
programáticamente, ej. "solo promover si mejora al mejor run actual"):

```python
from mlflow.tracking import MlflowClient

client = MlflowClient()
experimento = client.get_experiment_by_name("mi-proyecto")

runs = client.search_runs(
    experiment_ids=[experimento.experiment_id],
    order_by=["metrics.rmse ASC"],
    max_results=5,
)
mejor_run = runs[0]
print(mejor_run.info.run_id, mejor_run.data.metrics["rmse"])
```

**Model Registry** (versionar y promover un modelo a producción):

```python
resultado = mlflow.register_model(
    model_uri=f"runs:/{mejor_run.info.run_id}/model",
    name="mi-modelo-produccion",
)

client.transition_model_version_stage(
    name="mi-modelo-produccion",
    version=resultado.version,
    stage="Production",   # "Staging" | "Production" | "Archived"
)
```

---

## 4. Cargar (load) un modelo ya logueado

**Por `run_id` + nombre del artefacto** (para reproducir un experimento
puntual):

```python
import mlflow

modelo = mlflow.sklearn.load_model(f"runs:/{run_id}/model")
predicciones = modelo.predict(X_nuevo)
```

**Por Model Registry + stage** (para inferencia en producción — así el
código consumidor no depende de un `run_id` fijo, siempre toma la versión
promovida a `Production`):

```python
modelo = mlflow.pyfunc.load_model("models:/mi-modelo-produccion/Production")
predicciones = modelo.predict(X_nuevo)
```

Esto funciona igual desde un notebook de JupyterHub, desde un flow de
Prefect, o desde un script en Streamlit — mientras tengan
`MLFLOW_TRACKING_URI` y las credenciales S3 configuradas (sección 0).

---

## 5. Reentrenar un modelo y actualizar la versión en producción

Entender esto es clave: **"Production" es una etiqueta (stage) sobre una
versión concreta del Model Registry, no "el modelo" en sí**. Cada vez que
registras un modelo con `mlflow.register_model(...)` bajo el mismo `name`,
se crea una **versión nueva** (`version=1`, `2`, `3`, ...) — la anterior no
se sobreescribe ni se borra. Por eso reentrenar nunca afecta lo que ya está
en producción: quien consume el modelo con
`models:/mi-modelo-produccion/Production` sigue recibiendo la versión que
tenga esa etiqueta hasta que **tú explícitamente** se la asignes a la
versión nueva.

Flujo típico: reentrenar → registrar como nueva versión → comparar contra
la versión actual en `Production` → promover solo si mejora.

### 5.1 Reentrenar y registrar (código, ej. dentro de un flow de Prefect)

```python
import mlflow
from mlflow.tracking import MlflowClient

NOMBRE_MODELO = "mi-modelo-produccion"

mlflow.set_experiment("mi-proyecto")
with mlflow.start_run(run_name="reentrenamiento"):
    modelo = entrenar(X, y)   # tu función, con datos nuevos

    metrica_nueva = evaluar(modelo, X_test, y_test)
    mlflow.log_metric("rmse", metrica_nueva)
    mlflow.sklearn.log_model(modelo, "model")

    run_id = mlflow.active_run().info.run_id

# Registra la NUEVA versión (no toca la que esté en Production)
resultado = mlflow.register_model(
    model_uri=f"runs:/{run_id}/model",
    name=NOMBRE_MODELO,
)
version_nueva = resultado.version
print(f"✓ Registrada versión {version_nueva} (todavía sin stage)")
```

En este punto la versión nueva existe en el Registry pero **no sirve
tráfico**: `models:/mi-modelo-produccion/Production` sigue devolviendo la
versión anterior.

### 5.2 Comparar contra la versión actual en producción antes de promover

```python
client = MlflowClient()

version_actual_prod = client.get_latest_versions(NOMBRE_MODELO, stages=["Production"])
if version_actual_prod:
    run_actual = client.get_run(version_actual_prod[0].run_id)
    metrica_actual = run_actual.data.metrics["rmse"]
else:
    metrica_actual = float("inf")   # no hay versión en producción todavía

if metrica_nueva < metrica_actual:
    client.transition_model_version_stage(
        name=NOMBRE_MODELO,
        version=version_nueva,
        stage="Production",
        archive_existing_versions=True,   # manda la versión anterior a "Archived"
    )
    print(f"✓ Versión {version_nueva} promovida a Production (rmse {metrica_nueva} < {metrica_actual})")
else:
    print(f"✗ Versión {version_nueva} no mejora ({metrica_nueva} >= {metrica_actual}), se queda sin promover")
```

`archive_existing_versions=True` es lo que hace el reemplazo "atómico": la
versión que estaba en `Production` pasa a `Archived` en la misma llamada,
así nunca hay dos versiones simultáneas marcadas como `Production` (el
Registry lo permitiría técnicamente, pero rompe la garantía de "una sola
versión activa" que asume `models:/nombre/Production`).

### 5.3 ¿Se puede hacer la promoción desde la UI? Sí

No hace falta código para promover manualmente:

1. En `http://SERVER_IP:5000`, pestaña **Models** (arriba) → abre
   `mi-modelo-produccion`.
2. Verás la lista de versiones (1, 2, 3...) con su stage actual. Haz clic
   en la versión que acabas de registrar.
3. En el detalle de la versión, el dropdown **Stage** → **Transition to** →
   **Production**.
4. MLflow pregunta si quieres archivar automáticamente las demás versiones
   que estén en `Production` (equivalente a `archive_existing_versions=True`)
   — normalmente quieres decir que sí, para no dejar dos versiones activas.

Lo mismo funciona para volver atrás: si la versión nueva resulta mala en
producción, entra a la versión **anterior** y transitiónala de vuelta a
`Production` (con el mismo diálogo de archivar la actual). No hay que
reentrenar ni volver a subir nada — el artefacto de la versión anterior
sigue completo en `s3://artifacts/`.

### 5.4 Automatizar todo el ciclo desde Prefect

El patrón de 5.1 + 5.2 combinado en una sola `@task` (entrenar → registrar
→ comparar → promover condicionalmente) es exactamente lo que conviene
poner en un flow programado (ver
[PREFECT_JUPYTER_GUIDE.md](PREFECT_JUPYTER_GUIDE.md) para deployar y
programar), para que el reentrenamiento periódico solo reemplace el modelo
en producción cuando el nuevo de verdad mejora, sin intervención manual.

---

## 6. Usar MLflow desde fuera del servidor (otra máquina)

El proyecto está desplegado en un servidor remoto (`SERVER_IP` en `.env`),
no en `localhost`. Para usar el tracking server o cargar/loguear modelos
desde tu laptop u otra máquina que **no** está en la red Docker `ds_network`:

### 6.1 Requisitos de red

- El servidor debe tener los puertos **5000** (MLflow) y **9000** (MinIO,
  necesario porque los artefactos viajan directo cliente→MinIO, no a través
  de MLflow) alcanzables desde tu máquina — abiertos en el firewall/security
  group. El puerto **9001** (consola web de MinIO) es opcional, solo para
  inspección manual.
- Si el servidor está detrás de una VPN o requiere túnel SSH, ya deberías
  poder resolver `SERVER_IP` o hacer port-forward antes de seguir.

### 6.2 Variables de entorno en tu máquina

```bash
export MLFLOW_TRACKING_URI=http://<SERVER_IP>:5000
export MLFLOW_S3_ENDPOINT_URL=http://<SERVER_IP>:9000
export AWS_ACCESS_KEY_ID=<MINIO_ROOT_USER>       # mismo valor que en el .env del servidor
export AWS_SECRET_ACCESS_KEY=<MINIO_ROOT_PASSWORD>
```

En Python (alternativa a exportar variables de entorno):

```python
import os
os.environ["MLFLOW_TRACKING_URI"] = "http://<SERVER_IP>:5000"
os.environ["MLFLOW_S3_ENDPOINT_URL"] = "http://<SERVER_IP>:9000"
os.environ["AWS_ACCESS_KEY_ID"] = "<MINIO_ROOT_USER>"
os.environ["AWS_SECRET_ACCESS_KEY"] = "<MINIO_ROOT_PASSWORD>"

import mlflow
modelo = mlflow.pyfunc.load_model("models:/mi-modelo-produccion/Production")
```

Instala en tu entorno local el mismo rango de `mlflow` que corre el servidor
(`mlflow/Dockerfile`: `mlflow>=2.10,<3`) y `boto3`, para evitar
incompatibilidades de metadata al cargar modelos:

```bash
pip install "mlflow>=2.10,<3" boto3
```

### 6.3 Seguridad

⚠️ Las credenciales (`MINIO_ROOT_USER`/`PASSWORD`) que usa MLflow para leer/
escribir en S3 **son las mismas credenciales root de MinIO** — no hay un
usuario de solo-lectura separado en este stack. Compartirlas fuera del
servidor da acceso de lectura/escritura a **todos** los buckets
(`raw-data`, `processed-data`, `models`, `artifacts`), no solo a MLflow.
Si necesitas dar acceso externo a alguien que no debería tocar los otros
buckets, crea un usuario/policy de solo-lectura en MinIO
(`mc admin user add` / `mc admin policy attach`) en vez de repartir las
credenciales root.

Ni MLflow ni MinIO tienen TLS configurado en este stack — el tráfico
externo (incluidas las credenciales) va en texto plano salvo que agregues
un reverse proxy con HTTPS delante, o uses un túnel SSH/VPN.

### 6.4 Aplicar cambios en el servidor

Después de editar `docker-compose.yml` (ej. las variables agregadas a
`prefect-worker` en la sección 0), en el servidor:

```bash
docker compose config          # valida sintaxis antes de aplicar
docker compose up -d prefect-worker
```

No hace falta reconstruir la imagen (`docker compose build`) para un cambio
de solo variables de entorno, solo recrear el contenedor.

---

## Troubleshooting

| Síntoma | Causa probable | Qué revisar |
|---|---|---|
| `mlflow.exceptions.MlflowException: API request ... failed with exception ConnectionError` | `MLFLOW_TRACKING_URI` apunta a la URL equivocada (`http://mlflow:5000` no resuelve fuera de `ds_network`) | Desde fuera del servidor usa `http://SERVER_IP:5000`, no el nombre del servicio Docker |
| El run se crea pero falla al subir el modelo (`Could not find bucket`, `EndpointConnectionError`) | `MLFLOW_S3_ENDPOINT_URL` no configurado o credenciales S3 ausentes | Verifica `MLFLOW_S3_ENDPOINT_URL`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` en el entorno del proceso que loguea |
| `ModuleNotFoundError: No module named 'mlflow'` al correr un deployment de Prefect | Falta `mlflow` en `prefect-worker/Dockerfile` (ya debería estar) | `docker exec -it ds_prefect_worker pip show mlflow`; si falta, agrégalo al Dockerfile y `docker compose build prefect-worker` |
| Modelo carga distinto/falla al deserializar desde otra máquina | Versión de `mlflow`/`scikit-learn`/etc. distinta entre servidor y cliente | Iguala versiones, o revisa el archivo `requirements.txt`/`conda.yaml` que MLflow guarda junto al modelo en el artifact store |
| La UI de MLflow no carga en `http://SERVER_IP:5000` | Contenedor `ds_mlflow` caído o puerto no expuesto/bloqueado por firewall | `docker compose ps mlflow`, `docker compose logs mlflow`; confirma el puerto 5000 abierto en el firewall del servidor |
