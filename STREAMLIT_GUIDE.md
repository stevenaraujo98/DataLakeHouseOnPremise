# Guía de dashboards Streamlit multi-proyecto

Cómo está organizado `dashboards/`, cómo agregar un proyecto nuevo para un
cliente, y cómo migrar el enrutamiento cuando haya un dominio propio.

Documentation: 
- [Chart](https://docs.streamlit.io/develop/api-reference/charts)
- [Streamlit component](https://streamlit.io/components?category=all)

## Arquitectura

```
Internet/LAN
     │
     ▼
 ┌─────────┐   PathPrefix /proyecto-demo-1  ┌──────────────────────────┐
 │ traefik │ ───────────────────────────────▶ dashboard-proyecto-demo-1 │ (login propio)
 │  :80    │   PathPrefix /chatbot-th       ┌──────────────────────────┐
 │         │ ───────────────────────────────▶ dashboard-chatbot-th      │ (login propio)
 └─────────┘

 dashboard-internal (:8501, sin Traefik, sin login) → vista operativa del stack
```

- **`traefik`**: reverse proxy configurado con el **provider de archivos**
  (`traefik/dynamic/*.yml`), no con el provider de Docker. Se probó el
  provider de Docker (auto-descubrimiento por labels) y falló en el
  servidor real: el cliente Docker que trae compilado Traefik v3.1 pide
  fijo la API `1.24` sin negociar, y un daemon Docker reciente (API `1.40+`)
  la rechaza (`client version 1.24 is too old...`) — `DOCKER_API_VERSION`
  no lo soluciona porque Traefik no lee esa variable. El provider de
  archivos evita el socket de Docker por completo y enruta por el DNS
  interno de la red de compose (`http://dashboard-<proyecto>:8501`).
  Con `--providers.file.watch=true`, agregar un archivo nuevo en
  `traefik/dynamic/` no requiere reiniciar Traefik.
- **`dashboard-internal`** (`dashboards/_internal/`): el dashboard de estado
  del stack que ya existía, sin autenticación, publicado directo en `:8501`
  como antes. Es una vista tuya, no de clientes.
- **Un contenedor Streamlit por proyecto de cliente** (`dashboards/<proyecto>/`):
  aislado del resto — su propio `Dockerfile`, su propio `config.yaml` de
  usuarios, su propia cookie de sesión, su propia ruta (`/`\<proyecto>`).
  No publica puerto en el host: solo Traefik lo alcanza, dentro de `ds_network`.
- **`dashboards/common/`**: código de autenticación compartido
  (`auth.py`, `generate_hash.py`). Se monta como volumen de solo lectura
  (`/app/common`) en cada proyecto, así que un cambio en `auth.py` aplica a
  todos los proyectos sin reconstruir imágenes — solo `docker compose restart`.
- **`dashboards/_template/`**: plantilla para clonar cada vez que hay un
  proyecto/cliente nuevo.

## Autenticación

Cada proyecto tiene su propio `config.yaml` con usuarios (`streamlit-authenticator`,
hashes bcrypt) y un campo `role` por usuario (`cliente` o `admin`, aunque
puedes usar los roles que necesites). `dashboards/common/auth.py` expone
`login_gate()`, que:
1. Muestra el formulario de login.
2. Detiene la app (`st.stop()`) si no hay sesión válida.
3. Devuelve `(username, role)` para que el `app.py` del proyecto gatee
   secciones según el rol.

El login usuario/contraseña siempre está disponible. **Microsoft Entra ID
(SSO) es opcional y por proyecto**: se activa solo si existe
`dashboards/<proyecto>/.streamlit/secrets.toml` — mientras ese archivo no
exista en un proyecto, el botón "Iniciar sesión con Microsoft" ni siquiera
aparece, así que activar esto en un proyecto no afecta a los demás ni al
login usuario/contraseña que ya funciona. Ver la sección "Login con
Microsoft Entra ID" más abajo para el paso a paso.

## Cómo agregar un proyecto de dashboard nuevo

1. Clonar la plantilla:
   ```bash
   cp -r dashboards/_template dashboards/<nombre-proyecto>
   cp dashboards/<nombre-proyecto>/config.yaml.example dashboards/<nombre-proyecto>/config.yaml
   ```
2. Generar el hash de cada contraseña (no se guardan en texto plano):
   ```bash
   python dashboards/common/generate_hash.py
   # o: python dashboards/common/generate_hash.py "MiClave123!"
   ```
3. Completar `dashboards/<nombre-proyecto>/config.yaml`:
   - Un usuario por persona/cliente, con el hash generado en el paso 2.
   - `cookie.name` único (ej. `<nombre-proyecto>_auth`) y `cookie.key`
     aleatorio (`python -c "import secrets; print(secrets.token_hex(16))"`).
4. Editar `dashboards/<nombre-proyecto>/app.py` con el contenido real del
   dashboard (mantén la llamada a `login_gate()` al inicio).
5. Agregar el servicio en `docker-compose.yml` — copia el bloque de
   `dashboard-proyecto-demo-1`, y cambia:
   - Nombre del servicio y `container_name`
   - `build:` y los `volumes:` que apuntan a `dashboards/<nombre-proyecto>`
   - `--server.baseUrlPath=/<nombre-proyecto>` en el `command:`
6. Crear `traefik/dynamic/<nombre-proyecto>.yml`:
   ```yaml
   http:
     routers:
       <nombre-proyecto>:
         rule: "PathPrefix(`/<nombre-proyecto>`)"
         service: <nombre-proyecto>
     services:
       <nombre-proyecto>:
         loadBalancer:
           servers:
             - url: "http://dashboard-<nombre-proyecto>:8501"
   ```
   Traefik lo detecta solo (`--providers.file.watch=true`), no hace falta reiniciarlo.
7. Levantar el servicio:
   ```bash
   docker compose up -d --build dashboard-<nombre-proyecto>

   <!-- Ejemplo real -->
   sudo docker compose up -d --build --remove-orphans dashboard-proyecto-demo-1 dashboard-chatbot-th
   ```
8. URL para compartir con el cliente: `http://SERVER_IP/<nombre-proyecto>`

## Cómo actualizar un dashboard existente

Actualizar **los datos**, **el código de la interfaz** y **la imagen del
contenedor** son acciones distintas. Si los datos cambian pero la interfaz
sigue igual, comprobar qué versión de `app.py` está ejecutando el servidor.

Los comandos siguientes se ejecutan en el **servidor Linux/WSL**, desde la
raíz del repositorio utilizado por Docker Compose. Primero definir el
proyecto que se quiere actualizar, sustituyendo `nombre-proyecto` por su
nombre real:

```bash
PROYECTO="nombre-proyecto"
SERVICIO="dashboard-${PROYECTO}"
```

El patrón de esta guía usa `dashboards/<proyecto>/`, el servicio
`dashboard-<proyecto>` y la URL `http://SERVER_IP/<proyecto>`. Si un proyecto
usa otros nombres, ajustar las variables y las rutas a su configuración.

### Elegir la acción según lo que cambió

| Cambio | Acción en el servidor |
|---|---|
| Solo datos de MinIO, una base de datos o una API | Ejecutar el procesamiento y publicar los resultados. Renovar la caché según lo implementado en el dashboard. |
| `app.py` u otros archivos Python del proyecto | Actualizar los archivos en el servidor y reiniciar solo el dashboard afectado. La carpeta del proyecto se monta en `/app`. |
| Código compartido en `dashboards/common/` | Actualizarlo y reiniciar los dashboards que utilicen ese código. |
| `requirements.txt` o `Dockerfile` | Reconstruir la imagen y recrear el servicio. Un reinicio no instala dependencias. |
| Variables del contenedor en `.env`, `command:` u otra configuración de Compose | Validar y recrear el servicio para aplicar la configuración nueva. |
| Ruta en `traefik/dynamic/<proyecto>.yml` | Actualizar el archivo en el servidor. El provider de archivos lo detecta con `watch=true`. |

### Actualizar el código y comprobar el archivo montado

1. Llevar los archivos nuevos a `dashboards/<proyecto>/` en el repositorio
   del servidor, mediante Git o copia de archivos. Modificar la copia de tu
   computadora no modifica automáticamente la del servidor.
2. Si el servicio está ejecutándose, comparar el archivo del servidor con el
   que ve el contenedor:

   ```bash
   sha256sum "dashboards/${PROYECTO}/app.py"
   sudo docker compose exec -T "$SERVICIO" sha256sum /app/app.py
   ```

   Ambos hashes deben coincidir. Comparar también con la versión que se
   pretende desplegar: dos archivos antiguos pueden tener el mismo hash.
   Si difieren, revisar qué carpeta está montada realmente:

   ```bash
   ID_CONTENEDOR_DASHBOARD=$(sudo docker compose ps -q "$SERVICIO")
   sudo docker inspect "$ID_CONTENEDOR_DASHBOARD" --format '{{range .Mounts}}{{println .Source "->" .Destination}}{{end}}'
   ```

3. Si solo cambió código Python, reiniciar el servicio:

   ```bash
   sudo docker compose restart "$SERVICIO"
   sudo docker compose ps "$SERVICIO"
   sudo docker compose logs --tail=80 "$SERVICIO"

   <!-- Ejemplo -->
   sudo docker compose logs --tail=80 dashboard-chatbot-th
   ```

   Si el servicio todavía no existe, crearlo con
   `sudo docker compose up -d "$SERVICIO"` antes de comprobar sus archivos.
   En el patrón de este repositorio, el código se lee del bind mount
   `./dashboards/<proyecto>:/app`. Reconstruir la imagen no sustituye la
   actualización de esa carpeta. Además, `up -d --build` puede conservar el
   contenedor existente si su imagen y configuración no cambiaron; un
   reinicio asegura que se vuelva a ejecutar el código montado.

4. Abrir `http://SERVER_IP/<proyecto>`, recargar con `Ctrl+F5` e iniciar
   sesión. Comprobar las vistas modificadas y los permisos de cada rol.
   El puerto `:8501` corresponde al dashboard interno del stack; los
   proyectos de clientes se acceden por su ruta a través de Traefik.

### Actualizar dependencias o configuración del contenedor

Si cambió `requirements.txt` o el `Dockerfile`, actualizar los archivos del
servidor y ejecutar:

```bash
sudo docker compose build "$SERVICIO"
sudo docker compose up -d --no-deps "$SERVICIO"
```

Si cambiaron las variables de entorno o la configuración del servicio:

```bash
sudo docker compose config --quiet
sudo docker compose up -d --no-deps --force-recreate "$SERVICIO"
```

La recreación explícita también asegura que se apliquen los cambios de un
`env_file`. Después, revisar el estado y los logs del servicio. Estas
operaciones se limitan al dashboard afectado; no requieren reiniciar todo
el stack.

### Actualizar y publicar los datos

Ejecutar el notebook, flow o proceso de actualización que corresponda al
proyecto y confirmar que publicó los resultados en la fuente que consulta
`app.py`. Preparar tablas o archivos en memoria no equivale a publicarlos.
Si se trabaja desde JupyterHub, ejecutar también las celdas de escritura o
subida y comprobar que finalizaron correctamente.

Verificar que los archivos o tablas relacionados correspondan a la misma
actualización y que su formato sea compatible con la app. Por ejemplo,
actualizar el detalle no garantiza que los agregados también estén
actualizados. Cada proyecto define sus rutas, nombres de archivos y esquema.

Renovar la caché con el control que ofrezca el dashboard, si existe, o esperar
el tiempo de expiración configurado. Actualizar los datos no requiere
reconstruir la imagen. Si un proceso programado escribe sobre los mismos
resultados, mantenerlo compatible con el esquema que consume la interfaz.

Los notebooks están excluidos de Git por `notebooks/*`; se sincronizan por
separado cuando forman parte del procedimiento del proyecto.

### Diagnóstico si no se ven los cambios o no carga la página

| Síntoma | Qué comprobar |
|---|---|
| Los datos son nuevos, pero la interfaz es la anterior | Versión de `app.py` en el servidor y dentro del contenedor, bind mount y URL; después reiniciar y recargar el navegador. |
| La interfaz es nueva, pero muestra datos anteriores | Fuente consultada, fecha de publicación, caché y procesos programados que puedan sobrescribir los resultados. |
| La app informa de un formato incompatible | Compatibilidad entre los datos publicados y las columnas o campos que espera el código. |
| Se ve el login, pero no las gráficas | Inicio de sesión, permisos del rol, mensajes de la app y logs del servicio. |
| Hay errores al leer la fuente de datos | Conexión, permisos y existencia de los archivos o tablas esperados. |
| Página totalmente en blanco o cargando indefinidamente | Logs, recursos estáticos, conexión WebSocket y coincidencia entre la ruta de Traefik y `server.baseUrlPath`. |
| HTTP 404 o 502 | Ruta de Traefik, estado del dashboard y conexión entre contenedores. |

Para separar un problema del proceso Streamlit de uno del proxy, con el
patrón de rutas y puerto interno de esta guía:

```bash
sudo docker compose ps "$SERVICIO" traefik
sudo docker compose logs --tail=100 "$SERVICIO" traefik
sudo docker compose exec -T "$SERVICIO" python -c 'import sys; from urllib.request import urlopen; r = urlopen(f"http://127.0.0.1:8501/{sys.argv[1]}/_stcore/health", timeout=10); print(r.status, r.read().decode())' "$PROYECTO"
curl --max-time 10 -i "http://localhost/${PROYECTO}/_stcore/health"
```

Las dos consultas deberían responder `200` y `ok`. Si solo funciona la
consulta interna, revisar Traefik y su ruta. Un health check correcto no
confirma que el código de la app ni la lectura de datos funcionen: revisar
los logs al abrir la página.

Si continúa en blanco, abrir las herramientas de desarrollador del navegador
(`F12`), revisar **Console** y **Network → WS**, y comprobar la conexión a
`/<proyecto>/_stcore/stream`. Cuando Streamlit utiliza ese `baseUrlPath`,
Traefik debe conservar el prefijo. Para despliegues con subdominio y
`baseUrlPath` vacío, omitir el prefijo en las consultas de salud y WebSocket.

Referencias oficiales: [configuración de Streamlit](https://docs.streamlit.io/develop/api-reference/configuration/config.toml),
[problemas de carga remota](https://docs.streamlit.io/knowledge-base/deploy/remote-start)
y [comprobación de salud en Docker](https://docs.streamlit.io/deploy/tutorials/docker).

## Proyectos de ejemplo

`dashboards/proyecto-demo-1` es un proyecto funcional de ejemplo, pensado
para verificar el patrón end-to-end antes de crear proyectos reales:

- `http://SERVER_IP/proyecto-demo-1` — usuarios `cliente1` / `Demo1234!` y
  `admin1` / `Admin1234!`

Un usuario de un proyecto no puede iniciar sesión en el otro. Bórralo
cuando ya no lo necesites como referencia.

`proyecto-demo-2` dejó de existir como demo: se renombró a
`dashboards/chatbot-th`, el dashboard real de analítica del chatbot de
Talento Humano (ver `dashboards/chatbot-th/app.py`). Sigue teniendo
credenciales heredadas de la demo (`config.yaml` trae un `TODO` al
respecto) — reemplázalas antes de compartir la URL con usuarios reales.

- `http://SERVER_IP/chatbot-th` — usuarios `cliente2` / `Demo5678!` y
  `admin2` / `Admin5678!`

## Login con Microsoft Entra ID (opcional, por proyecto)

Basado en la [guía oficial de Streamlit para Microsoft](https://docs.streamlit.io/develop/tutorials/authentication/microsoft).
Es **opcional y no afecta nada mientras no lo configures**: sin
`.streamlit/secrets.toml`, un proyecto sigue funcionando solo con
usuario/contraseña, exactamente igual que ahora.

### 1. Lo que tienes que hacer TÚ en Azure Portal (una sola vez, cuenta de administrador)

Esto requiere la cuenta de administrador de tu organización en Microsoft
Entra ID — es un registro de aplicación único, compartido por todos los
proyectos de dashboards (cada proyecto solo necesita su propio Redirect URI
dentro de esa misma app).

1. Entra a [portal.azure.com](https://portal.azure.com) → **Microsoft Entra ID** → **App registrations** → **New registration**.
2. Nombre: algo identificable, ej. `DataLakeHouse Dashboards`.
3. **Supported account types**: normalmente *"Accounts in this organizational directory only"* (single-tenant), salvo que quieras permitir cuentas de otras organizaciones.
4. **Redirect URI**: puedes dejarlo vacío por ahora, se agrega en el paso 6. Clic en **Register**.
5. En la página **Overview** de la app recién creada, copia:
   - **Application (client) ID**
   - **Directory (tenant) ID**
6. Ve a **Authentication** → **Add a platform** → **Web**. Ahí agregas **un Redirect URI por cada proyecto** que vaya a tener login con Microsoft:
   - `http://SERVER_IP/proyecto-demo-1/oauth2callback`
   - `http://SERVER_IP/chatbot-th/oauth2callback`
   - (y así por cada proyecto nuevo que actives; cuando exista dominio, agrega también la versión `https://<proyecto>.midominio.com/oauth2callback` — ver más abajo)
7. Ve a **Certificates & secrets** → **New client secret** → copia el **Value** apenas se genera (no se vuelve a mostrar). Ese es tu `client_secret`.
8. En **API permissions**, confirma que estén `openid`, `email`, `profile` (suelen venir por defecto vía Microsoft Graph). Si tu organización lo exige, usa **Grant admin consent**.

Con esto ya tienes los 4 datos que piden los proyectos: `client_id`, `tenant_id` (dentro de la URL `server_metadata_url`), `client_secret`, y los `redirect_uri` (uno por proyecto).

### 2. Lo que se hace por cada proyecto que quiera login con Microsoft

1. Copiar la plantilla de secretos:
   ```bash
   cp dashboards/<proyecto>/.streamlit/secrets.toml.example dashboards/<proyecto>/.streamlit/secrets.toml
   ```
   (si el proyecto no tiene carpeta `.streamlit/`, créala: `mkdir -p dashboards/<proyecto>/.streamlit`)
2. Completar `dashboards/<proyecto>/.streamlit/secrets.toml` con los datos de Azure Portal (paso 1) y un `cookie_secret` propio (`python -c "import secrets; print(secrets.token_hex(32))"`). **Este archivo no se sube a git** (ya está en `.gitignore`) — solo vive en el servidor.
3. Agregar la sección `entra:` en `dashboards/<proyecto>/config.yaml` con los correos que sí deben poder entrar con Microsoft y su rol (ver `config.yaml.example`). Un correo del tenant que no esté listado ahí **no puede entrar**, aunque el login con Microsoft funcione — es la misma lógica de acceso restringido que ya tiene el login usuario/contraseña.
4. Reconstruir el contenedor (el `requirements.txt` de la plantilla ya incluye `Authlib`, necesario para `st.login()`):
   ```bash
   docker compose up -d --build dashboard-<proyecto>
   ```
5. Probar en `http://SERVER_IP/<proyecto>` — debe seguir apareciendo el login usuario/contraseña de siempre, más un botón "Iniciar sesión con Microsoft" debajo.

### Mientras tanto (antes de configurar Azure)

No hace falta hacer nada para que el stack siga funcionando: sin
`secrets.toml`, `dashboards/common/auth.py` detecta que no hay config de
Entra y ni siquiera intenta llamar a `st.login()` — los proyectos existentes
(`proyecto-demo-1`, `chatbot-th`) y cualquier proyecto nuevo siguen
funcionando solo con usuario/contraseña hasta que decidas activarlo.

## Migrar a un dominio propio (subdominios + HTTPS)

Hoy el enrutamiento es por `PathPrefix` sobre la IP del servidor porque no
hay dominio. Si se consigue un dominio wildcard (`*.midominio.com → IP del
servidor`), migrar a subdominio por proyecto es un cambio de unas pocas
líneas por proyecto, sin tocar el código de las apps:

1. En `traefik`, agregar el resolver de Let's Encrypt (HTTP challenge — 
   funciona automático porque el wildcard DNS ya resuelve cualquier
   subdominio hacia el servidor):
   ```yaml
   command:
     - "--providers.file.directory=/etc/traefik/dynamic"
     - "--providers.file.watch=true"
     - "--entrypoints.web.address=:80"
     - "--entrypoints.websecure.address=:443"
     - "--certificatesresolvers.le.acme.httpchallenge=true"
     - "--certificatesresolvers.le.acme.httpchallenge.entrypoint=web"
     - "--certificatesresolvers.le.acme.email=tu-email@dominio.com"
     - "--certificatesresolvers.le.acme.storage=/letsencrypt/acme.json"
   ports:
     - "80:80"
     - "443:443"
   volumes:
     - ./traefik/dynamic:/etc/traefik/dynamic:ro
     - /data/datascience/traefik:/letsencrypt
   ```
2. En cada `traefik/dynamic/<proyecto>.yml`, reemplazar la regla `PathPrefix` por `Host` y agregar TLS:
   ```yaml
   http:
     routers:
       <proyecto>:
         rule: "Host(`<proyecto>.midominio.com`)"
         service: <proyecto>
         tls:
           certResolver: le
     services:
       <proyecto>:
         loadBalancer:
           servers:
             - url: "http://dashboard-<proyecto>:8501"
   ```
3. Quitar `--server.baseUrlPath=/<proyecto>` del `command:` de Streamlit
   (ya no hace falta, cada proyecto vive en la raíz de su propio subdominio).
4. Compartir con el cliente `https://<proyecto>.midominio.com` en vez de
   `http://SERVER_IP/<proyecto>`.
5. Si el proyecto ya tenía login con Microsoft activo: en Azure Portal
   (**Authentication**) agrega el nuevo Redirect URI
   `https://<proyecto>.midominio.com/oauth2callback`, y actualiza
   `redirect_uri` en `dashboards/<proyecto>/.streamlit/secrets.toml` al
   mismo valor (puedes dejar también el viejo en Azure mientras migras,
   y quitarlo después).
