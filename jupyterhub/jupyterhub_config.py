c = get_config()

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

# Base de datos en volumen persistente (sobrevive reinicios)
c.JupyterHub.db_url = 'sqlite:////srv/jupyterhub/jupyterhub.sqlite'
c.JupyterHub.cookie_secret_file = '/srv/jupyterhub/jupyterhub_cookie_secret'

# Directorio base de notebooks
c.Spawner.notebook_dir = '/home/{username}'

# Permitir ejecución como root dentro del contenedor
c.Spawner.cmd = ['jupyterhub-singleuser', '--allow-root']

# Reenviar variables de entorno de MinIO a los kernels de notebook
import os
c.Spawner.environment = {
    'MINIO_ENDPOINT':   os.environ.get('MINIO_ENDPOINT', ''),
    'MINIO_ACCESS_KEY': os.environ.get('MINIO_ACCESS_KEY', ''),
    'MINIO_SECRET_KEY': os.environ.get('MINIO_SECRET_KEY', ''),
}

# IP y puerto
c.JupyterHub.ip = '0.0.0.0'
c.JupyterHub.port = 8000

# Sin SSL directo (se usará proxy/Nginx si es producción)
# c.JupyterHub.ssl_cert = '/srv/jupyterhub/fullchain.pem'
# c.JupyterHub.ssl_key = '/srv/jupyterhub/privkey.pem'
