# Guía: de notebook a flow programado en Prefect (desde JupyterHub)

Pasos para que un usuario de JupyterHub convierta su análisis en un flow de
Prefect, lo pruebe, lo deploye, y controle cuándo se ejecuta — todo desde la
terminal de JupyterHub, sin tocar los contenedores `ds_prefect` / `ds_prefect_worker`.

Contexto (ver también [AGENTS.md](AGENTS.md), sección "Prefect flows: org / shared / users"):
- El servidor `prefect` (`ds_prefect`) solo es API + UI. El que **ejecuta** los flows
  es el servicio `prefect-worker` (`ds_prefect_worker`), que debe estar corriendo
  (`docker compose ps prefect-worker`) para que cualquier deployment funcione.
- Tareas compartidas (conexión a Postgres/MinIO, etc.) viven en
  [flows/common_tasks.py](flows/common_tasks.py) y se importan con
  `from common_tasks import ...` desde cualquier flow, gracias a `PYTHONPATH`.

---

## 0. Dónde trabajar

Cada usuario tiene su carpeta en JupyterHub, que es la misma que
`/data/datascience/notebooks/{usuario}/` en el host:

```
/home/{usuario}/{proyecto}/
├── 1_analisis.ipynb      ← notebook de desarrollo
└── mi_flow.py            ← flow que crearás en el paso 2
```

Ejemplo real ya existente: `/home/admin/analisis_chat_th/` (con `1_process.ipynb`
y `main.ipynb`; el flow correspondiente vive en el repo como
[flows/analisis_chat_th.py](flows/analisis_chat_th.py), un flow **organizacional**
porque lo mantiene el equipo, no un solo usuario — para un flow personal, el
`.py` va directo en tu carpeta, no en el repo).

⚠️ **Ese mismo directorio también existe en JupyterHub bajo una segunda
ruta: `/flows/users/{usuario}/{proyecto}/`** (mismos archivos, otra puerta
de entrada). Es la ruta idéntica a la que ven los `prefect-worker-*` que
ejecutan tus flows. Desarrolla/edita donde te sea cómodo (`/home/...`), pero
**cuando vayas a correr `prefect deploy` (paso 4), hazlo parado en
`/flows/users/{usuario}/{proyecto}/`**, no en `/home/...` — así la ruta que
Prefect guarda para el flow es la misma que el worker realmente tiene
disponible, y no falla al ejecutarse por no encontrar el archivo. Lo mismo
aplica a flows organizacionales: usa `/flows/org/...`, no `/srv/flows/org/...`.

---

## 1. Desarrollar y validar en el notebook

Trabaja normalmente en tu `.ipynb` hasta que el código funcione: leer de
Postgres, transformar, guardar en MinIO, etc.

## 2. Convertir el notebook a un flow de Prefect

Crea `mi_flow.py` en la misma carpeta, junto al notebook:

```python
from prefect import flow, task
from common_tasks import connect_postgres, cerrar_conexion, leer_query, \
    conectar_minio, subir_dataframe_csv

@task
def mi_transformacion(df):
    # tu lógica aquí
    return df

@flow(name="mi-flow")
def mi_flow():
    conexion = connect_postgres(database="saacdata")
    try:
        df = leer_query(conexion, "SELECT * FROM mi_tabla")
        df = mi_transformacion(df)

        s3 = conectar_minio()
        subir_dataframe_csv(s3, df, bucket="processed-data", key="mi_area/resultado.csv")
    finally:
        cerrar_conexion(conexion)

if __name__ == "__main__":
    mi_flow()
```

## 3. Probar el flow en la terminal de JupyterHub (ejecución local)

Abre una terminal en JupyterHub (`File > New > Terminal`) y corre:

```bash
cd /home/{tu_usuario}/{tu_proyecto}
python mi_flow.py
```

Esto ejecuta el flow **en ese mismo proceso** (no pasa por `prefect-worker`),
pero como `PREFECT_API_URL` ya está configurado, el run queda registrado y
visible en `http://SERVER_IP:4200`. Es la forma rápida de depurar antes de
deployar.

## 4. Deployar (registrar el flow en Prefect Server)

Revisar también el paso 5 para elegir el pool.
El entrypoint va con el nombre real de la función @flow.

Párate en la ruta `/flows/...` (ver ⚠️ del paso 0), no en `/home/...` ni
`/srv/flows/...`:
```bash
cd /flows/users/{tu_usuario}/{tu_proyecto}
prefect deploy mi_flow.py:mi_flow --name "mi-flow-prod" --pool chats --tag th
```

Ejemplo real (flow organizacional, ruta `/flows/org`):
```bash
cd /flows/org
prefect deploy analisis_chat_th.py:analisis_chat_th_flow --name "analisis-chat-th" --pool chats --tag th
```

- El `entrypoint` (`archivo.py:nombre`) tiene que ser el **nombre real de la
  función Python** decorada con `@flow`, no el nombre del archivo ni el
  `name="..."` que le pusiste al `@flow(...)`. En `analisis_chat_th.py` la
  función se llama `analisis_chat_th_flow` — si pones otra cosa, `prefect
  deploy` falla con `MissingFlowError` y te sugiere el nombre correcto.
- Si te pregunta `Would you like your workers to pull your flow code from a
  remote storage location...? [y/n]`, responde **`n`**. El código ya está
  disponible localmente para los workers (mismos bind mounts); decir "y" te
  manda por el camino de storage remoto vía git, y la imagen no tiene el
  binario `git` instalado (`FileNotFoundError: 'git'`).
- El CLI puede hacerte 1-2 preguntas interactivas más la primera vez (ej. si
  quieres agregar un schedule ahora). Si no quieres que se ejecute todavía
  automáticamente, responde que no / omite el schedule — ver el paso 7.
- Si prefieres evitar los prompts interactivos: `export PREFECT_CLI_PROMPT=false`
  antes de correr `prefect deploy`.

En este punto el deployment existe en `http://SERVER_IP:4200/deployments`,
pero **todavía no se ejecuta solo** a menos que le hayas puesto un schedule.

## 5. ¿Qué work pool uso?

Hay 4 pools, cada uno con su propio worker corriendo permanentemente. Los
primeros 3 agrupan por **tipo de carga** (no por unidad/proyecto individual —
un concurrency-limit es sobre todo un control de recursos del servidor, y
proyectos del mismo tipo se parecen en eso aunque sean de unidades
distintas); el cuarto es un comodín:

| Pool | `--concurrency-limit` | Para |
|---|---|---|
| `chats` | 3 | Análisis de chats de n8n por unidad (TH, académico, bienestar, ...) |
| `training` | 1 | Entrenamiento de modelos (riesgo académico, planificación académica, ODS, carreras, ...) — serializado a propósito para no saturar CPU/RAM del servidor |
| `dashboards` | 20 | Procesamiento de datos para dashboards — jobs más livianos, pero van a ser varios |
| `default` | 2 | Comodín: algo que todavía no encaja claramente en los 3 de arriba (pruebas puntuales, un flow nuevo mientras decides su tipo). Límite bajo a propósito porque no se sabe de antemano qué tan pesado será lo que caiga aquí. |

```bash
prefect deploy mi_flow.py:mi_flow --name "mi-flow-prod" --pool chats --tag th
```

Distingue proyecto/unidad con `--tag` (`--tag th`, `--tag academico`, ...),
no creando un pool nuevo por unidad — así el número de workers no crece sin
control a medida que agregues proyectos. Filtra por tag en la UI.

`default` es para lo que no tienes claro todavía, no para "lo dejo ahí
porque no quiero pensar en cuál usar". Si algo que aterrizó en `default`
resulta ser recurrente, muévelo a su pool por tipo (mismo `prefect deploy`,
solo cambia `--pool`). Si tampoco encaja en ninguno de los 4 (un tipo de
carga totalmente nuevo y ya sabes que va a ser recurrente), avisa para
decidir si conviene un quinto pool+worker en vez de forzarlo en `default`
(se agrega copiando el bloque `x-prefect-worker-common` de
`docker-compose.yml`).

`--pool <nombre>` **no se crea solo**: si el pool no existe, `prefect deploy`
falla (o pregunta interactivamente, pero nunca lo crea en modo no
interactivo). Los 4 de arriba ya existen — se crean solos la primera vez que
arranca cada worker (`prefect work-pool create ... || true` en su
`command`). Si más adelante cambias el `--concurrency-limit` de uno que ya
existe, ese `|| true` no lo actualiza (create no-opea si ya existe); usa:
```bash
prefect work-pool update chats --concurrency-limit 5
```

## 6. Ejecutarlo inmediatamente (sin esperar ninguna programación)

Esto es lo que quieres para "mandarlo ahora": crea un flow run que el
worker de ese pool recoge de inmediato (normalmente en segundos) porque
siempre está haciendo polling.

**Desde la UI:** `Deployments` → tu deployment → botón **Run** → **Quick run**.

**Desde la terminal de JupyterHub:**
```bash
prefect deployment run 'mi-flow/mi-flow-prod'
```
(el formato es `'<nombre-del-flow>/<nombre-del-deployment>'`, con comillas
por la barra).

Puedes hacer esto las veces que quieras, tenga o no un schedule configurado.

## 7. Programarlo para que corra cada cierto tiempo

⚠️ **La hora del cron es independiente del `TZ` del contenedor.** Prefect
guarda cada schedule con su propia zona horaria (por defecto UTC si no la
especificas), sin importar que `prefect-worker`/`jupyterhub` ya tengan
`TZ=America/Guayaquil`. Si programas `0 2 * * *` sin indicar zona, correrá a
las 2 AM **UTC** = 9 PM en Ecuador (UTC-5), no a las 2 AM de Ecuador.
Especifica siempre la zona al crear el schedule.

**Desde la UI (recomendado, no depende de la versión exacta del CLI):**
`Deployments` → tu deployment → **Create Schedule** → elige `Cron`
(ej. `0 2 * * *` = 2 AM diario) o `Interval`, y selecciona **Timezone:
America/Guayaquil** en el mismo diálogo.

**Desde la terminal:**
```bash
prefect deployment schedule create 'mi-flow/mi-flow-prod' --cron "0 2 * * *" --timezone "America/Guayaquil"
```
Si tu versión de Prefect usa otra sintaxis, confírmala con
`prefect deployment schedule --help`.

(La `TZ=America/Guayaquil` del contenedor sí importa para otra cosa: para
que `datetime.now()` dentro del código del flow, ej. el timestamp del
nombre del Excel en `analisis_chat_th.py`, refleje la hora de Ecuador — eso
es aparte de a qué hora dispara el schedule.)

## 8. Pausar la programación sin borrar el deployment

Útil cuando quieres dejar de correr automáticamente pero seguir pudiendo
correrlo manualmente (paso 6) o reactivarlo después.

**Desde la UI:** en la lista de schedules del deployment, apaga el toggle
**Active**.

**Desde la terminal:**
```bash
prefect deployment schedule ls 'mi-flow/mi-flow-prod'        # obtener el schedule id
prefect deployment schedule pause 'mi-flow/mi-flow-prod' <schedule_id>
prefect deployment schedule resume 'mi-flow/mi-flow-prod' <schedule_id>
```

## 9. Actualicé el script — ¿cómo aplico el cambio?

- **Solo cambiaste la lógica interna** (mismo archivo, misma función `@flow`,
  mismos parámetros): no hace falta re-deployar. `prefect-worker` lee el
  `.py` desde disco (bind mount) en cada ejecución nueva, así que el próximo
  run — manual o programado — ya usa el código actualizado. Basta con
  guardar el archivo.
- **Cambiaste el nombre de la función `@flow`, el nombre del archivo, los
  parámetros que recibe, o quieres actualizar nombre/descripción/tags del
  deployment**: vuelve a correr el mismo comando de deploy:
  ```bash
  prefect deploy mi_flow.py:mi_flow --name "mi-flow-prod" --pool default
  ```
  Como el nombre del deployment es el mismo, esto **actualiza** el
  deployment existente (mismo ID, mismo historial de runs) en vez de crear
  uno duplicado, y normalmente conserva el/los schedule(s) que ya tenía.
  Confirma la versión/descripción en la UI después.
- Para verificar el cambio sin esperar el próximo schedule, dispara un run
  manual (paso 6) y revisa los logs.

## 10. Detener una ejecución que ya está corriendo

Esto es distinto de pausar el schedule (que solo evita runs *futuros*).
Para cancelar un run que está **en curso ahora mismo**:

- **UI:** `Deployments` → tu deployment → pestaña de runs → abre el run
  activo → botón **Cancel**.
- **Terminal:**
  ```bash
  prefect flow-run ls --limit 5        # ver ids recientes y su estado
  prefect flow-run cancel <flow-run-id>
  ```

La cancelación es cooperativa: si el flow está en medio de algo bloqueante
(ej. una query SQL pesada), puede tardar unos segundos en detenerse de
verdad.

## 11. Eliminar la programación o el deployment completo

**Borrar solo un schedule** (el deployment sigue existiendo, puedes seguir
corriéndolo manual o ponerle un schedule nuevo después):
```bash
prefect deployment schedule ls 'mi-flow/mi-flow-prod'          # obtener el schedule id
prefect deployment schedule delete 'mi-flow/mi-flow-prod' <schedule_id>
```
En la UI: en la lista de schedules del deployment, ícono de basura junto al
schedule que quieras quitar.

**Borrar el deployment completo** (borra también sus schedules; tu
`mi_flow.py` en disco no se toca, solo se elimina el registro en Prefect):
```bash
prefect deployment delete 'mi-flow/mi-flow-prod'
```
En la UI: `Deployments` → tu deployment → menú `...` → **Delete**.

> Diferencia clave: *pausar* (paso 8) es reversible y mantiene el schedule
> guardado con un toggle; *eliminar* el schedule o el deployment no se
> puede deshacer — hay que volver a crearlo.

## 12. Verificar que corrió

- UI: `http://SERVER_IP:4200/deployments/deployment/<id>` → pestaña de runs, logs por task.
- Terminal: `docker compose logs -f prefect-worker` (en el servidor; si usas un pool
  dedicado como en el paso 5, revisa el servicio de worker correspondiente, ej.
  `docker compose logs -f prefect-worker-th`).

---

## Troubleshooting

| Síntoma | Causa probable | Qué revisar |
|---|---|---|
| El run se queda en `Scheduled`/`Late` para siempre | No hay ningún worker escuchando el pool del deployment (`prefect-worker` está caído, o deployaste a un pool nuevo sin worker propio — ver paso 5) | `docker compose ps`, `docker exec -it ds_prefect prefect work-pool ls`, `docker compose logs <servicio-del-worker>` |
| `ModuleNotFoundError` al correr el deployment (pero `python mi_flow.py` sí funcionó en JupyterHub) | La librería está en `jupyterhub/Dockerfile` pero no en `prefect-worker/Dockerfile` | Agrégala a `prefect-worker/Dockerfile` y `docker compose build prefect-worker` |
| `ImportError: No module named 'common_tasks'` | `PYTHONPATH` no llegó al proceso | Verifica `PYTHONPATH` en el entorno (`echo $PYTHONPATH`); en JupyterHub reinicia tu kernel/servidor para recoger cambios de `jupyterhub_config.py` |
| El deployment no aparece en la UI aunque el `prefect deploy` "funcionó" | Corriste `prefect deploy` desde `ds_prefect` (no desde JupyterHub) sin `PREFECT_API_URL`, y quedó en una API efímera local | Siempre deploya desde la terminal de JupyterHub, nunca con `docker exec -it ds_prefect ...` |
| `prefect deploy ... --pool th` falla diciendo que el pool no existe | `--pool` no crea el work pool automáticamente | `prefect work-pool create th --type process` antes de deployar — ver paso 5 |
| `FileNotFoundError: [Errno 2] No such file or directory: 'git'` al deployar | Respondiste "y" al prompt de storage remoto; la imagen no tiene `git` instalado | Responde `n` a esa pregunta — el código ya es local para los workers, no hace falta storage remoto |
| El deployment se crea bien pero el flow run falla al ejecutarse diciendo que no encuentra el `.py` | Deployaste parado en `/home/...` o `/srv/flows/...`; esa ruta no existe dentro del worker | Deploya parado en `/flows/users/{usuario}/{proyecto}` o `/flows/org` — ver ⚠️ del paso 0 |
