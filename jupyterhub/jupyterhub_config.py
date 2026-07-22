c = get_config()

import os

# Autenticación nativa (credenciales en base de datos persistente)
c.JupyterHub.authenticator_class = 'nativeauthenticator.NativeAuthenticator'

# Spawner
c.JupyterHub.spawner_class = 'simple'

# Admin users (pueden registrarse en /hub/signup y se aprueban automáticamente)
c.Authenticator.admin_users = {'admin'}

# Permitir que cualquier usuario registrado se loguee sin aprobación manual
c.NativeAuthenticator.open_signup = True

# Autorizar a todos los usuarios registrados (necesario en JupyterHub 4.x)
c.Authenticator.allow_all = True

# Base de datos persistente para usuarios, tokens y estado interno.
# Si no se define JUPYTERHUB_DB_URL, mantiene compatibilidad con SQLite.
c.JupyterHub.db_url = os.environ.get(
    'JUPYTERHUB_DB_URL',
    'sqlite:////srv/jupyterhub/jupyterhub.sqlite'
)
c.JupyterHub.cookie_secret_file = '/srv/jupyterhub/jupyterhub_cookie_secret'

# Directorio base de notebooks
c.Spawner.notebook_dir = '/home/{username}'

# Crear el directorio home del usuario si no existe antes de arrancar el servidor
async def pre_spawn_hook(spawner):
    import os
    username = spawner.user.name
    home_dir = f'/home/{username}'
    os.makedirs(home_dir, exist_ok=True)

c.Spawner.pre_spawn_hook = pre_spawn_hook

# Permitir ejecución como root dentro del contenedor
c.Spawner.cmd = ['jupyterhub-singleuser', '--allow-root']

# Reenviar credenciales a los notebooks/terminales de TODOS los usuarios.
#
# Este contenedor (ds_jupyterhub) ya tiene en su propio os.environ tanto lo
# de `env_file: .env` (docker-compose.yml) como los renames explícitos del
# `environment:` de este servicio (ej. AWS_ACCESS_KEY_ID <- MINIO_ROOT_USER
# para MLflow/boto3). Reenviamos por PREFIJO conocido en vez de listar cada
# variable a mano, para que cualquier credencial nueva que agregues al .env con
# uno de estos prefijos (Postgres, MinIO, AWS, MLflow, Prefect, OpenAI)
# quede disponible automáticamente para todos, sin tocar este archivo.
#
# Ojo: por eso NO reenviamos os.environ completo (`**os.environ` a secas)
# -- este mismo contenedor también tiene secretos internos de JupyterHub
# (JUPYTERHUB_API_TOKEN, cookie secret, etc.) que no deben terminar en el
# notebook de cada usuario.
_PASSTHROUGH_PREFIXES = (
    'POSTGRES_', 'MINIO_', 'AWS_', 'MLFLOW_',
    'PREFECT_', 'OPENAI_', 'OPEN_API_', 'SERVER_IP',
)
c.Spawner.environment = {
    key: value
    for key, value in os.environ.items()
    if key.startswith(_PASSTHROUGH_PREFIXES)
}
c.Spawner.environment.update({
    # Nombres que esperan flows/common_tasks.py y los flows (distintos de
    # los nombres crudos del .env) -- igual que en el `environment:` de
    # prefect-worker en docker-compose.yml.
    'POSTGRES_HOST':    'pgbouncer',
    'MINIO_ENDPOINT':   'http://minio:9000',
    'MINIO_ACCESS_KEY': os.environ.get('MINIO_ROOT_USER', ''),
    'MINIO_SECRET_KEY': os.environ.get('MINIO_ROOT_PASSWORD', ''),
    # Silenciar advertencia de Git en MLflow
    'GIT_PYTHON_REFRESH': 'quiet',
    # Permite `from common_tasks import ...` desde cualquier notebook/flow
    'PYTHONPATH': '/srv/flows/org:/srv/flows/shared',
})

# IP y puerto
c.JupyterHub.ip = '0.0.0.0'
c.JupyterHub.port = 8000

# Sin SSL directo (se usará proxy/Nginx si es producción)
# c.JupyterHub.ssl_cert = '/srv/jupyterhub/fullchain.pem'
# c.JupyterHub.ssl_key = '/srv/jupyterhub/privkey.pem'
