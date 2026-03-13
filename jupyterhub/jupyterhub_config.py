c = get_config()

# Autenticación simple (cambiar a LDAP en producción)
c.JupyterHub.authenticator_class = 'jupyterhub.auth.PAMAuthenticator'

# Spawner
c.JupyterHub.spawner_class = 'simple'

# Crear automáticamente usuarios del sistema si no existen
c.LocalAuthenticator.create_system_users = True

# Admin users
c.Authenticator.admin_users = {'admin'}

# Permitir que cualquier usuario del sistema se loguee
c.PAMAuthenticator.open_sessions = False

# Directorio base de notebooks
c.Spawner.notebook_dir = '/home/{username}'

# IP y puerto
c.JupyterHub.ip = '0.0.0.0'
c.JupyterHub.port = 8000

# Sin SSL directo (se usará proxy/Nginx si es producción)
# c.JupyterHub.ssl_cert = '/srv/jupyterhub/fullchain.pem'
# c.JupyterHub.ssl_key = '/srv/jupyterhub/privkey.pem'
