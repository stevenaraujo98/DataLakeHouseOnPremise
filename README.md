# Data Lakehouse
Stack de tecnologías para implementar un Data Lakehouse en un entorno on-premise
- PostgreSQL: Base de datos relacional para almacenamiento estructurado.
- MinIO: Almacenamiento de objetos compatible con S3 para datos no estructurados.
- MLflow: Plataforma de gestión de ciclo de vida de modelos de machine learning.
- Prefect: Orquestación de flujos de trabajo para automatizar tareas de datos.
- JupyterHub: Entorno de notebooks colaborativo para análisis de datos y desarrollo de modelos.
- Streamlit: Framework para crear aplicaciones web interactivas de datos.

Cada componente está configurado para utilizar almacenamiento persistente en un SSD local, asegurando un rendimiento óptimo para las operaciones de lectura y escritura de datos

### Estructura de carpetas en el servidor
En `/data` conviven dos árboles con propósitos distintos — no mezclar código con datos:

```
/data/
├── DataLakeHouseOnPremise/   ← este repo git (código: compose, Dockerfiles, flows organizacionales)
└── datascience/              ← datos en runtime (bind mounts, fuera de git)
    ├── notebooks/{usuario}/  ← home de cada usuario de JupyterHub = sus notebooks y sus flows personales
    ├── flows/                ← flows/utilidades compartidos entre usuarios (no van a git)
    ├── postgres/ minio/ prefect/ jupyterhub/ ...
```

Dentro de `DataLakeHouseOnPremise/` (build contexts y config, uno por servicio):
- `docker-compose.yml`: orquesta todo el stack.
- `flows/`: flows **organizacionales** versionados en git (ver [PREFECT_JUPYTER_GUIDE.md](PREFECT_JUPYTER_GUIDE.md)), incluye `common_tasks.py` con las tareas compartidas de Postgres/MinIO.
- `jupyterhub/`, `mlflow/`, `prefect-worker/`: `Dockerfile` (y config) de cada servicio.
- `dashboards/`: un contenedor Streamlit por proyecto, enrutados por Traefik (`dashboards/_internal/` = vista interna sin login en `:8501`; `dashboards/<proyecto>/` = un dashboard por cliente, con login propio; `dashboards/_template/` = plantilla para clonar; `dashboards/common/` = auth compartida). Ver [STREAMLIT_GUIDE.md](STREAMLIT_GUIDE.md).
- `notebooks/`: notebooks de ejemplo/plantilla versionados en git (ej. `Prefect_Jobs_Scheduler.ipynb`, `1_process.ipynb`), montados como `/srv/notebooks/examples` en JupyterHub — son solo referencia, distintos de los notebooks reales de cada usuario (esos viven en `datascience/notebooks/{usuario}/`, montados como `/home/{usuario}`).
- `sql/`: bootstrap inicial de PostgreSQL.
- `pgbouncer/`: config de referencia, hoy el servicio `pgbouncer` se configura solo por variables de entorno, no lee estos archivos.
- `diagrams/`: fuente de diagramas de arquitectura, no se usa en runtime.
- `AGENTS.md`, `ADITONAL.md`: guías operativas.
- `PREFECT_JUPYTER_GUIDE.md`, `STREAMLIT_GUIDE.md`: runbooks de Prefect/JupyterHub y de los dashboards Streamlit multi-proyecto.

> Si acabas de traer los cambios de `prefect-worker` (worker de Prefect) a este repo, en el servidor falta hacer `git pull` antes de `docker compose up -d --build` — sin eso, `docker-compose.yml` referenciará `./prefect-worker` pero esa carpeta todavía no existirá ahí.

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

### Linux
#### Variable de entorno
```bash
<!-- ***************************************************** -->
export POSTGRES_USER=
export POSTGRES_PASSWORD=
<!-- ***************************************************** -->
```

#### Permisos de usuario
```bash
sudo chown -R manager:manager /data/DataLakeHouseOnPremise

<!-- *************************************** -->
sudo chown -R manager:manager /data/datascience/
# Restaurar owner de postgres (UID 999 = usuario postgres dentro del contenedor)
sudo chown -R 999:999 /data/datascience/postgres
<!-- *************************************** -->

```

#### Horario servidor
Para ver el estado detallado del reloj, zona horaria y sincronización.
```bash
timedatectl
timedatectl status
date -u
uptime
ls -l /etc/localtime
```

Ver en el contenedor
```bash
sudo docker compose exec postgres psql -U "$POSTGRES_USER" -d saacdata -c "SHOW timezone; SELECT NOW();"
```

Cambiar zona del servidor local
```bash
# Listar zonas
timedatectl list-timezones
# Establecer zona
sudo timedatectl set-timezone America/Guayaquil
```

#### Ver almacenamiento
```
sudo du -sh /var/lib/
sudo du -h --max-depth=1 /var/lib/containerd/
sudo du -h --max-depth=1 /var/lib
sudo du -h --max-depth=1 /

sudo du -sh /data/
sudo du -sh /data/*
sudo du -h --max-depth=1 /data/

sudo df -h
sudo du -sh /*
```

#### Ver almacenamiento de docker y verificar
```bash
sudo docker system df
sudo docker system df -v

sudo containerd config dump | grep -m1 "^root"
sudo nano /etc/containerd/config.toml
sudo grep "^root" /etc/containerd/config.toml
sudo nano /etc/docker/daemon.json
```

#### Borrar
```bash
sudo rm -rf /data/backups/containerd.old.*
```

#### Liberar espacio
Primera solucion:  
Este comando eliminará todos los contenedores detenidos, redes no usadas e imágenes sin contenedores asociados.
```bash
<!-- ***************************************************** -->
sudo docker system prune -a --volumes
<!-- ***************************************************** -->
```

Desinstalando Docker de raiz:  
```
sudo systemctl stop docker docker.socket containerd
sudo apt-get purge -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo apt-get autoremove -y

<!-- # Desmontar todo lo relacionado con overlay y docker -->
sudo areas=$(mount | grep -E 'docker|containerd' | awk '{print $3}')
for m in $areas; do sudo umount -l $m; done

<!-- # Ahora borra las carpetas físicas -->
sudo rm -rf /var/lib/docker
sudo rm -rf /var/lib/containerd
sudo rm -rf /etc/docker/daemon.json

<!-- Verificar -->
df -h /
<!-- (El parámetro -x evita que du cuente otros discos como /data). -->
sudo du -hxd 1 / | sort -h
```

#### Cambiar imagenes de docker a /data
```
<!-- Reinstalar Docker -->
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io

<!-- Crea el nuevo directorio -->
sudo mkdir -p /data/docker
<!-- Configura el daemon -->
sudo nano /etc/docker/daemon.json
<!-- Pegar -->
{
  "data-root": "/data/docker"
}
<!-- Reinicia y verifica -->
sudo systemctl restart docker
# Verifica que la ruta cambió
docker info | grep "Docker Root Dir"
<!-- Debería decir: Docker Root Dir: /data/docker -->
```

#### Cambiar todo el codigo a /data
```bash
sudo mv ~/DataLakeHouseOnPremise /data/
<!-- Cambiar al nuevo directorio -->
cd /data/DataLakeHouseOnPremise
<!-- Corregir permisos (para que tu usuario 'manager' pueda editar sin sudo) -->
sudo chown -R manager:manager /data/DataLakeHouseOnPremise
<!-- Asegurar que las carpetas de datos existan en el SSD -->
sudo mkdir -p /data/datascience/{postgres,minio,prefect,jupyterhub,notebooks}
sudo chmod -R 775 /data/datascience/

<!-- *************************************** -->
sudo chown -R manager:manager /data/datascience/
# Restaurar owner de postgres (UID 999 = usuario postgres dentro del contenedor)
sudo chown -R 999:999 /data/datascience/postgres
<!-- *************************************** -->
```

### Docker
#### Base
```bash
# Bajar todos los servicios
sudo docker compose down
# Bajar todos los servicios y eliminar los volúmenes
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
sudo docker compose logs -f mlflow

sudo docker logs -f ds_jupyterhub
sudo docker logs -f ds_postgres
sudo docker logs -f ds_prefect

# Ver contenedores en ejecución
sudo docker ps
# ver todos los contenedores, incluyendo los detenidos
sudo docker ps -a

# Veri imagebes y Volumenes
sudo docker image ls
sudo docker images
sudo docker volume ls
sudo docker network ls
```

#### Reiniciar servicios
Nota: Los datos en /data/datascience/postgres, /data/datascience/minio, etc. nunca se tocan con --rmi all. Ese flag solo afecta las imágenes Docker, no los volúmenes montados del host.

##### Reiniciar solo un servicio específico (actualizacion de compose, py y dockerfile)
Se conserva todo lo demás, solo se reinicia el servicio que quieras. Si se hace cambio en el codigo como app.py se necesita restart.
```bash
cd /data/DataLakeHouseOnPremise

# Ejemplo. El volumen ya lo monta en vivo
docker compose restart postgres
docker compose restart minio
docker compose restart mlflow
docker compose restart prefect
docker compose restart jupyterhub
docker compose restart dashboard-internal
docker compose restart dashboard-proyecto-demo-1
```  

Si reconstruiste la imagen, cambiaste código o Dockerfile de un servicio:
```bash
sudo docker compose up -d --build postgres
sudo docker compose up -d --build minio
sudo docker compose up -d --build mlflow
sudo docker compose up -d --build prefect
sudo docker compose up -d --build jupyterhub
sudo docker compose up -d --build traefik dashboard-internal dashboard-proyecto-demo-1 dashboard-proyecto-demo-2
```
Nota: al renombrar/agregar servicios de dashboards en `docker-compose.yml`, usa `--remove-orphans` la primera vez para limpiar el contenedor viejo `ds_streamlit`:
```bash
sudo docker compose up -d --build --remove-orphans
```

Ejemplo de cambio en docker-compose.yml, jupyterhub_config.py y Dockerfile para jupyterhub 
```bash
sudo docker compose build jupyterhub
sudo docker compose up -d jupyterhub
sudo docker compose logs -f jupyterhub
sudo docker exec -it ds_postgres psql -U "$POSTGRES_USER" -d jupyterhub -c "\dt"
```

##### Eliminar y recrear solo un contenedor sin tocar datos
```bash
sudo docker compose stop postgres
sudo docker compose rm -f postgres
sudo docker compose up -d postgres
```

##### Reiniciar todo sin perder nada
Bajar todo el stack y volverlo a subir sin perder datos:
Se conserva imagenes, datos. Reinicio normal. Cambios en docker-compose.yml, no se necesita reconstruir imágenes.

```bash
cd /data/DataLakeHouseOnPremise
sudo docker compose down
sudo docker compose up -d
```

##### Reiniciar las imágenes sin perder datos
Se reconstruyen las imágenes pero se conservan los datos. Útil si hiciste cambios en el Dockerfile o en la configuración de los servicios.
```bash
<!-- ***************************************************** -->
cd /data/DataLakeHouseOnPremise

# Bajar contenedores y eliminar solo las imágenes
sudo docker compose down --rmi all

# Reconstruir imágenes y levantar
sudo docker compose build --no-cache
sudo docker compose up -d
<!-- ***************************************************** -->
```

##### Actualizar una imagen base
Si quieres actualizar la imagen base (por ejemplo, si usas una imagen de Python y quieres la última versión), puedes hacer un pull de la imagen base y luego reconstruir tus imágenes.
```bash
cd /data/DataLakeHouseOnPremise

# Bajar contenedores y eliminar solo las imágenes
sudo docker compose down --rmi all

# Levantar el compose
sudo docker compose up -d
```



##### Reinicio limpio (borra TODO)
Se elimina todo datos, imagenes, volúmenes. Se levanta todo desde cero.
```bash
<!-- ***************************************************** -->
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

# limpar cache
sudo docker system prune -a --volumes
# actualizar repo
sudo git pull
# compilar y ejecutar 
sudo docker compose up -d --build

# o
# Reconstruir imágenes y levantar desde cero
sudo docker compose build --no-cache
sudo docker compose up -d
<!-- ***************************************************** -->
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
- Dashboard interno (estado del stack) = http://192.168.10.59:8501/ (dashboard interno, sin login)
- Proyecto demo 1 = http://192.168.10.59/proyecto-demo-1 (dashboard de cliente, con login — ver [STREAMLIT_GUIDE.md](STREAMLIT_GUIDE.md))
- Proyecto demo 2 = http://192.168.10.59/proyecto-demo-2 (dashboard de cliente, con login)
- MLflow = http://192.168.10.59:5000
- MinIO API (S3) = http://192.168.10.59:9000
- MinIO Console = http://192.168.10.59:9001
- Prefect UI/API = http://192.168.10.59:4200
- JupyterHub = http://192.168.10.59:8000

### Funcionalidad
Conectarse a base de datos con las credenciales env.  


En JupyterHub crear el usuario admin en http://192.168.10.59:8000/hub/signup.  
Usar librerias:
- %pip install -qqq librerias
- !pip install -q --no-input librerias  
Ya por defecto viene preinstalado "pandas scikit-learn mlflow boto3 s3fs"  

---

Acceder al MinIO http://192.168.10.59:9001/browser/artifacts
Puerto 9000 vs 9001 en MinIO  
Puerto	Uso  
9000	API S3 — para operaciones programáticas (boto3, mc, SDK)  
9001	Consola web (UI) — interfaz de administración en el navegador  

```
import boto3

s3 = boto3.client(
    's3',
    endpoint_url=os.environ["MLFLOW_S3_ENDPOINT_URL"],
    aws_access_key_id=os.environ["AWS_ACCESS_KEY_ID"], 
    aws_secret_access_key=os.environ["AWS_SECRET_ACCESS_KEY"]
)

s3.upload_file('data.csv', 'raw-data', 'data.csv')
```

fecha/lote/modelo
- s3://raw-data/bronze/...
- s3://processed-data/silver/...
- s3://processed-data/gold/...
- s3://processed-data/features/customer_features/v2026_03_13/...

---

MlFlow 
```
import mlflow
import mlflow.sklearn
from sklearn.linear_model import LinearRegression

mlflow.set_tracking_uri("http://mlflow:5000")
mlflow.set_experiment("demo_experiment") # lo crea

# Leer desde MinIO
df = pd.read_csv("data.csv")

X = df[["x", "y"]]
y = df["target"]

with mlflow.start_run():
    model = LinearRegression()
    model.fit(X, y)

    mlflow.log_param("model_type", "LinearRegression")
    mlflow.log_metric("score", model.score(X, y))

    mlflow.sklearn.log_model(model, "model")
```

---
Streamlit ya no es un único dashboard en el puerto 8501: ahora es un dashboard
interno (sigue en `:8501`, sin login) más N dashboards de cliente, cada uno en
su propio contenedor y ruta (`/proyecto-x`), enrutados por Traefik en el
puerto 80, con login propio. Ver [STREAMLIT_GUIDE.md](STREAMLIT_GUIDE.md).
