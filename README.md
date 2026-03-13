# Data Lakehouse
Stack de tecnologías para implementar un Data Lakehouse en un entorno on-premise
- PostgreSQL: Base de datos relacional para almacenamiento estructurado.
- MinIO: Almacenamiento de objetos compatible con S3 para datos no estructurados.
- MLflow: Plataforma de gestión de ciclo de vida de modelos de machine learning.
- Prefect: Orquestación de flujos de trabajo para automatizar tareas de datos.
- JupyterHub: Entorno de notebooks colaborativo para análisis de datos y desarrollo de modelos.
- Streamlit: Framework para crear aplicaciones web interactivas de datos.

Cada componente está configurado para utilizar almacenamiento persistente en un SSD local, asegurando un rendimiento óptimo para las operaciones de lectura y escritura de datos

### Consideraciones
#### Crear usuario en JupyterHub
```bash
# Entrar al contenedor de JupyterHub
sudo docker exec -it ds_jupyterhub bash

# Crear el usuario admin (el que definiste en JUPYTERHUB_ADMIN)
useradd -m admin

# Asignarle una contraseña (te la pedirá dos veces)
passwd admin

# Salir del contenedor
exit
```

### Docker
```bash
# Bajar todos los servicios
sudo docker-compose down
# Bajar todos los servicios y eliminar los volúmenes (¡cuidado, se perderán los datos!)
sudo docker-compose down -v
# Bajar todos los servicios, volúmenes e imágenes 
sudo docker-compose down -v --rmi all

# Levantar solo Postgres primero para verificar la inicialización
sudo docker compose up -d postgres
# Subir todos los servicios start and build
sudo docker-compose up -d

#  Ver todos los logs
sudo docker compose logs -f
# Ver logs de un servicio específico
sudo docker compose logs -f jupyterhub
sudo docker compose logs -f postgres

# Ver contenedores en ejecución
sudo docker ps
# ver todos los contenedores, incluyendo los detenidos
sudo docker ps -a
```
