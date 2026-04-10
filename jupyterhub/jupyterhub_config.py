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

# Reenviar variables de entorno de MinIO y MLflow a los kernels de notebook
c.Spawner.environment = {
    # Credenciales S3-compatibles requeridas por MLflow/boto3
    'AWS_ACCESS_KEY_ID':     os.environ.get('AWS_ACCESS_KEY_ID', ''),
    'AWS_SECRET_ACCESS_KEY': os.environ.get('AWS_SECRET_ACCESS_KEY', ''),
    'MLFLOW_S3_ENDPOINT_URL': os.environ.get('MLFLOW_S3_ENDPOINT_URL', ''),
    # URI del servidor MLflow
    'MLFLOW_TRACKING_URI':   os.environ.get('MLFLOW_TRACKING_URI', ''),
    # URL del servidor Prefect dedicado
    'PREFECT_API_URL':        os.environ.get('PREFECT_API_URL', ''),
    # Silenciar advertencia de Git en MLflow
    'GIT_PYTHON_REFRESH':    'quiet',
}

# IP y puerto
c.JupyterHub.ip = '0.0.0.0'
c.JupyterHub.port = 8000

# Sin SSL directo (se usará proxy/Nginx si es producción)
# c.JupyterHub.ssl_cert = '/srv/jupyterhub/fullchain.pem'
# c.JupyterHub.ssl_key = '/srv/jupyterhub/privkey.pem'
