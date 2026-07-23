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
  `PYTHONPATH` es lo que Python usa para buscar módulos al hacer import.

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
y `main.ipynb`). El flow correspondiente, `analisis_chat_th.py`, es
**organizacional** porque lo mantiene el equipo — su versión oficial vive en
el repo como [flows/analisis_chat_th.py](flows/analisis_chat_th.py) (mientras
no se suba a git, la única copia real es la de esta carpeta de usuario, ver
Troubleshooting). Reutiliza las tasks compartidas de
[flows/common_tasks.py](flows/common_tasks.py) (no es un flow, es el módulo
del que cualquier flow importa `connect_postgres`, `conectar_minio`, etc. —
ver el paso 2). Para un flow personal (no compartido con el equipo), el `.py`
va directo en tu carpeta, no en el repo.

**Ese mismo directorio también existe en JupyterHub bajo una segunda
ruta: `/flows/users/{usuario}/{proyecto}/`** IMPORTANTE (mismos archivos, otra puerta
de entrada). Es la ruta idéntica a la que ven los `prefect-worker-*` que
ejecutan tus flows. Desarrolla/edita donde te sea cómodo (`/home/...`), pero
**cuando vayas a correr `prefect deploy` (paso 4), hazlo desde la ruta
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
    conectar_minio, subir_dataframe_archivo

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
        subir_dataframe_archivo(s3, df, bucket="processed-data", key="mi_area/resultado.csv")
    finally:
        cerrar_conexion(conexion)

if __name__ == "__main__":
    mi_flow()
```

`from common_tasks import ...` funciona aunque `mi_flow.py` y `common_tasks.py`
estén en carpetas distintas (ej. tu flow en `/flows/users/admin/...` y
`common_tasks.py` en `/flows/org`) — no es magia de rutas relativas, es que
`/flows/org` (y `/flows/shared`) está en `PYTHONPATH`, la variable de entorno
que Python revisa para encontrar módulos a importar, sin importar desde qué
directorio se ejecuta el script. Está seteada tanto en JupyterHub como en
cada `prefect-worker-*` (ver `docker-compose.yml` y `jupyterhub_config.py`),
así que el import resuelve igual en los dos lados.

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
prefect deploy mi_flow.py:mi_flow --name "mi-flow-prod" --pool default
```

Ejemplo real: `analisis_chat_th.py` **debería** deployarse desde `/flows/org`
(es organizacional), pero mientras no esté subida a git esa carpeta no tiene
el archivo — hoy por hoy solo existe la copia en la carpeta personal de
`admin`, así que se deploya desde ahí:
```bash
cd /flows/users/admin/analisis_chat_th
prefect deploy analisis_chat_th.py:analisis_chat_th_flow --name "analisis-chat-th" --pool chats --tag th
```
El día que se suba a git y aparezca en `/flows/org/analisis_chat_th.py`, hay
que volver a correr este mismo comando parado en `/flows/org` — mismo
`--name`, así que actualiza el deployment existente (ver paso 9) en vez de
duplicarlo, pero **sí cuenta como redeploy** porque cambia la ruta desde
donde se registra, aunque la función `@flow` en sí no haya cambiado.

- El `entrypoint` (`archivo.py:nombre`) tiene que ser el **nombre real de la
  función Python** decorada con `@flow`, no el nombre del archivo ni el
  `name="..."` que le pusiste al `@flow(...)`. En `analisis_chat_th.py` la
  función se llama `analisis_chat_th_flow` — si pones otra cosa, `prefect
  deploy` falla con `MissingFlowError` y te sugiere el nombre correcto.
- El CLI puede hacer 2-3 preguntas interactivas la primera vez para un
  deployment sin `prefect.yaml`; para un deploy simple sin schedule
  automático, responder que no a todas funciona:
  - `Would you like your workers to pull your flow code from a remote
    storage location...? [y/n]` → **`n`**. El código ya está disponible
    localmente para los workers (mismos bind mounts); decir "y" te manda por
    el camino de storage remoto vía git, y la imagen no tiene el binario
    `git` instalado (`FileNotFoundError: 'git'`).
  - Si pregunta por agregar un schedule ahora → **`n`** si no quieres que se
    ejecute todavía automáticamente (puedes agregarlo después, ver el paso 7).
  - Si pregunta por guardar la configuración en un `prefect.yaml` → tu
    respuesta, no afecta lo demás de esta guía.
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

Formato del cron: `Minuto Hora Día_del_mes Mes Día_de_la_semana`. Ejemplo
`0 20 * * *` = minuto 0, hora 20 (8 PM en formato 24h), todos los días del
mes/meses/días de la semana → **todos los días a las 8 PM**.

⚠️ **Esa hora se interpreta en la zona que le pongas al schedule — no en el
`TZ` del contenedor.** Prefect guarda cada schedule con su propia zona
horaria, por defecto **UTC** si no especificas `--timezone`, sin importar
que `prefect-worker`/`jupyterhub` ya tengan `TZ=America/Guayaquil`. Dos
escenarios distintos:

- **Con `--timezone "America/Guayaquil"` (recomendado, siempre hazlo así):**
  el número de hora que escribes en el cron **ya es hora de Ecuador**, sin
  convertir nada. `0 20 * * *` + `--timezone "America/Guayaquil"` = 8 PM en
  Ecuador, directo.
- **Sin `--timezone` (el error a evitar):** Prefect asume UTC, y ahí sí hay
  que convertir. `0 2 * * *` sin zona corre a las 2 AM **UTC**, que son las
  **9 PM del día anterior** en Ecuador (UTC-5): `02:00 − 5h = -03:00`, y esa
  hora negativa "retrocede" al día anterior a las 21:00. Por eso siempre hay
  que pasar `--timezone` — así nunca tienes que hacer esta resta a mano.

**Desde la UI (recomendado, no depende de la versión exacta del CLI):**
`Deployments` → tu deployment → **+ Schedule** → elige `Cron`
(ej. `0 20 * * *` = 8 PM diario) o `Interval`, y selecciona **Timezone:
America/Guayaquil** en el mismo diálogo.

**Desde la terminal:**
```bash
prefect deployment schedule create 'mi-flow/mi-flow-prod' --cron "0 20 * * *" --timezone "America/Guayaquil"
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
  mismos parámetros, **en la misma ruta desde donde ya deployaste** — ver
  el aviso del paso 4 sobre `/flows/org` vs `/flows/users/...`): no hace
  falta re-deployar. El worker lee el `.py` desde disco (bind mount) en cada
  ejecución nueva, así que el próximo run — manual o programado — ya usa el
  código actualizado. Basta con guardar el archivo.
- **Cambiaste el nombre de la función `@flow`, el nombre del archivo, la
  ruta desde donde se deploya, los parámetros que recibe, o quieres
  actualizar nombre/descripción/tags del deployment**: vuelve a correr el
  mismo comando de deploy. Ejemplo real:
  ```bash
  prefect deploy analisis_chat_th.py:analisis_chat_th_flow --name "analisis-chat-th" --pool chats --tag th
  ```
  Como el nombre del deployment es el mismo, esto **actualiza** el
  deployment existente (mismo ID, mismo historial de runs) en vez de crear
  uno duplicado, y normalmente conserva el/los schedule(s) que ya tenía.
  Confirma la versión/descripción en la UI después.

**Cómo comprobar que de verdad corrió el código nuevo** (útil sobre todo
cuando el cambio fue "solo lógica interna" y no hay nada visible en la UI
que lo confirme):

1. Dispara un run manual (paso 6) en vez de esperar el próximo schedule.
2. En la UI, abre ese run y mira los nombres de las **tasks** que ejecutó.
   Si el cambio reemplazó una task por otra (ej. al mover
   `analisis_chat_th.py` a usar `common_tasks.py`, la task
   `"Descargar dataframe procesado anterior"` desapareció y quedó
   `"Descargar CSV o XLSX o Parquet desde MinIO"`), verla en el run
   confirma que sí se está ejecutando el archivo actualizado.
3. Si el cambio no se nota en los nombres de las tasks, la forma más segura
   y genérica: agrega temporalmente un `print("PRUEBA-123")` al inicio del
   `@flow`, corre un run manual, confirma que aparece en los logs, y
   quítalo. Simple, pero funciona siempre sin importar qué haya cambiado.

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
| Un flow "organizacional" (ej. `analisis_chat_th.py`) no aparece en `/flows/org`, solo `common_tasks.py` | El archivo se editó localmente en el repo pero nunca se hizo `git add`/`commit`/`push` — `git pull` en el servidor no puede traer algo que nunca se subió | Revisa `git status` en el repo local; si aparece como sin trackear, pide que se suba, luego `git pull` en el servidor |
