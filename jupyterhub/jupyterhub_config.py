c = get_config()

# Autenticación simple (cambiar a LDAP en producción)
c.JupyterHub.authenticator_class = 'jupyterhub.auth.PAMAuthenticator'

# Spawner
c.JupyterHub.spawner_class = 'simple'

# Admin users
c.Authenticator.admin_users = {'admin'}

# Permitir que cualquier usuario del sistema se loguee
c.PAMAuthenticator.open_sessions = False

# Directorio base de notebooks
c.Spawner.notebook_dir = '/home/{username}'

# IP y puerto
c.JupyterHub.ip = '0.0.0.0'
c.JupyterHub.port = 8000

# Deshabilitar SSL (usar nginx/proxy en producción)
c.JupyterHub.ssl_cert = ''
c.JupyterHub.ssl_key = ''