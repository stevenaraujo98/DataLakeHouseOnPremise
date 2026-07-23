# Guía de dashboards Streamlit multi-proyecto

Cómo está organizado `dashboards/`, cómo agregar un proyecto nuevo para un
cliente, y cómo migrar el enrutamiento cuando haya un dominio propio.

## Arquitectura

```
Internet/LAN
     │
     ▼
 ┌─────────┐   PathPrefix /proyecto-demo-1  ┌──────────────────────────┐
 │ traefik │ ───────────────────────────────▶ dashboard-proyecto-demo-1 │ (login propio)
 │  :80    │   PathPrefix /proyecto-demo-2  ┌──────────────────────────┐
 │         │ ───────────────────────────────▶ dashboard-proyecto-demo-2 │ (login propio)
 └─────────┘

 dashboard-internal (:8501, sin Traefik, sin login) → vista operativa del stack
```

- **`traefik`**: reverse proxy que descubre servicios por labels de Docker.
  Agregar un proyecto nuevo nunca requiere tocar la config de Traefik —
  solo agregar un servicio con sus propios labels en `docker-compose.yml`.
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

Esto es username/contraseña por ahora. Cuando se migre a **Microsoft Entra
ID** (SSO), el único archivo que cambia es `dashboards/common/auth.py`
(cambia la implementación interna de `login_gate`, la firma
`(username, role)` se mantiene) — los `app.py` de cada proyecto no se tocan.

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
   - Los tres labels de Traefik (`routers.<nombre-proyecto>...`, `services.<nombre-proyecto>...`)
6. Levantar el servicio:
   ```bash
   docker compose up -d --build dashboard-<nombre-proyecto>
   ```
7. URL para compartir con el cliente: `http://SERVER_IP/<nombre-proyecto>`

## Proyectos de ejemplo

`dashboards/proyecto-demo-1` y `dashboards/proyecto-demo-2` son dos
proyectos funcionales de ejemplo, aislados entre sí (rutas, `config.yaml`,
usuarios y cookies distintos), pensados para verificar el patrón end-to-end
antes de crear proyectos reales:

- `http://SERVER_IP/proyecto-demo-1` — usuarios `cliente1` / `Demo1234!` y
  `admin1` / `Admin1234!`
- `http://SERVER_IP/proyecto-demo-2` — usuarios `cliente2` / `Demo5678!` y
  `admin2` / `Admin5678!`

Un usuario de un proyecto no puede iniciar sesión en el otro. Bórralos
cuando ya no los necesites como referencia.

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
     - "--providers.docker=true"
     - "--providers.docker.exposedbydefault=false"
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
     - /var/run/docker.sock:/var/run/docker.sock:ro
     - /data/datascience/traefik:/letsencrypt
   ```
2. En cada proyecto, reemplazar los labels de `PathPrefix` por `Host`:
   ```yaml
   labels:
     - "traefik.enable=true"
     - "traefik.http.routers.<proyecto>.rule=Host(`<proyecto>.midominio.com`)"
     - "traefik.http.routers.<proyecto>.tls.certresolver=le"
     - "traefik.http.services.<proyecto>.loadbalancer.server.port=8501"
   ```
3. Quitar `--server.baseUrlPath=/<proyecto>` del `command:` de Streamlit
   (ya no hace falta, cada proyecto vive en la raíz de su propio subdominio).
4. Compartir con el cliente `https://<proyecto>.midominio.com` en vez de
   `http://SERVER_IP/<proyecto>`.
