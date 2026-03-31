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
sudo docker compose down
# Bajar todos los servicios y eliminar los volúmenes (¡cuidado, se perderán los datos!)
sudo docker compose down -v
# Bajar todos los servicios, volúmenes e imágenes 
sudo docker compose down -v --rmi all

# Construir las imágenes
sudo docker compose build

# Levantar solo Postgres primero para verificar la inicialización
sudo docker compose up -d postgres
# Subir todos los servicios start and build
sudo docker compose up -d

# Construir y subir los contenedores, forzando la reconstrucción de las imágenes
sudo docker compose up -d --build

#  Ver todos los logs
sudo docker compose logs -f

# Ver logs de un servicio específico
sudo docker compose logs -f jupyterhub
sudo docker compose logs -f postgres
sudo docker compose logs -f prefect

sudo docker logs -f ds_jupyterhub
sudo docker logs -f ds_postgres
sudo docker logs -f ds_prefect

sudodocker compose logs -f mlflow

# Ver contenedores en ejecución
sudo docker ps
# ver todos los contenedores, incluyendo los detenidos
sudo docker ps -a
```

#### Reiniciar servicios
Nota: Los datos en /data/datascience/postgres, /data/datascience/minio, etc. nunca se tocan con --rmi all. Ese flag solo afecta las imágenes Docker, no los volúmenes montados del host.

##### Reiniciar sin perder nada
Se conserva imagenes, datos. Reinicio normal. Cambios en docker-compose.yml, no se necesita reconstruir imágenes.
- cd /home/manager/DataLakeHouseOnPremise

```bash
cd ~/DataLakeHouseOnPremise
sudo docker compose down
sudo docker compose up -d
```

##### Reiniciar imágenes sin perder datos
Se reconstruyen las imágenes pero se conservan los datos. Útil si hiciste cambios en el Dockerfile o en la configuración de los servicios.
```bash
cd ~/DataLakeHouseOnPremise

# Bajar contenedores y eliminar solo las imágenes
sudo docker compose down --rmi all

# Reconstruir imágenes y levantar
sudo docker compose build --no-cache
sudo docker compose up -d
```

##### Actualizar una imagen base
Si quieres actualizar la imagen base (por ejemplo, si usas una imagen de Python y quieres la última versión), puedes hacer un pull de la imagen base y luego reconstruir tus imágenes.
```bash
cd ~/DataLakeHouseOnPremise

# Bajar contenedores y eliminar solo las imágenes
sudo docker compose down --rmi all

# Levantar el compose
sudo docker compose up -d
```

##### Reiniciar solo un servicio específico
Se conserva todo lo demás, solo se reinicia el servicio que quieras. Si se hace cambio en el codigo como app.py se necesita restart.
```bash
cd ~/DataLakeHouseOnPremise

# Ejemplo con mlflow (cambia el nombre según necesites) el volumen ya lo monta en vivo
sudo docker compose restart mlflow

# O si reconstruiste la imagen:
sudo docker compose up -d --build mlflow
```

##### Reinicio limpio (borra TODO)
Se elimina todo datos, imagenes, volúmenes. Se levanta todo desde cero.
```bash
cd ~/DataLakeHouseOnPremise

# Bajar contenedores y eliminar volúmenes Docker
sudo docker compose down -v --rmi all

# Borrar datos persistentes del SSD
sudo rm -rf /data/datascience/minio/*
sudo rm -rf /data/datascience/jupyterhub/*
sudo rm -rf /data/datascience/mlflow/*
sudo rm -rf /data/datascience/postgres/*
sudo rm -rf /data/datascience/postgres
sudo mkdir -p /data/datascience/postgres
sudo chmod 777 /data/datascience/postgres

# Reconstruir imágenes y levantar desde cero
sudo docker compose build --no-cache
sudo docker compose up -d
# o
sudo docker compose up -d --build
```


### Reiniciar la base de datos
```bash
cd ~/DataLakeHouseOnPremise

# 1. Detener el contenedor
sudo docker compose stop postgres

# 2. Borrar los datos del SSD (esto fuerza la re-inicialización)
sudo rm -rf /data/datascience/postgres/*

# Forzar la eliminación de datos de postgres (opcional, si quieres eliminar completamente la base de datos y empezar desde cero)
sudo rm -rf /data/datascience/postgres
sudo mkdir -p /data/datascience/postgres
sudo chmod 777 /data/datascience/postgres

# 3. Levantar Postgres de nuevo
sudo docker compose up -d postgres

# 4. Ver los logs inmediatamente
sudo docker compose logs -f postgres

# 5. Verificar que la base de datos se haya inicializado correctamente
sudo docker exec -it ds_postgres psql -U postgres -c "\l"
```

### Servidores levantados
- http://192.168.10.59:8501/
- http://192.168.10.59:5000/
- http://192.168.10.59:9001/
- http://192.168.10.59:4200/
- http://192.168.10.59:8000/
- 
