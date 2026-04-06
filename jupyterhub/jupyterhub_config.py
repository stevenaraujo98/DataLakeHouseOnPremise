c = get_config()

# Autenticación nativa (credenciales en base de datos persistente)
c.JupyterHub.authenticator_class = 'nativeauthenticator.NativeAuthenticator'

# Spawner
c.JupyterHub.spawner_class = 'simple'

# Admin users (pueden registrarse en /hub/signup y se aprueban automáticamente)
c.Authenticator.admin_users = {'admin'}

# Permitir que cualquier usuario registrado se loguee sin aprobación manual
c.NativeAuthenticator.open_signup = True

# Directorio base de notebooks
c.Spawner.notebook_dir = '/home/{username}'

# IP y puerto
c.JupyterHub.ip = '0.0.0.0'
c.JupyterHub.port = 8000

# Sin SSL directo (se usará proxy/Nginx si es producción)
# c.JupyterHub.ssl_cert = '/srv/jupyterhub/fullchain.pem'
# c.JupyterHub.ssl_key = '/srv/jupyterhub/privkey.pem'
