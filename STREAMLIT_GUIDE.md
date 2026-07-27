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
   ```
8. URL para compartir con el cliente: `http://SERVER_IP/<nombre-proyecto>`

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
