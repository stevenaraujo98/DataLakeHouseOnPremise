# Operación adicional

## Docker
- ¿Para qué sirven los healthchecks?
Son la forma en que Docker sabe si un contenedor está realmente listo para recibir tráfico, no solo si el proceso arrancó.
Sin healthcheck, Docker considera un contenedor "listo" en cuanto el proceso inicia — pero Postgres puede tardar 3-5 segundos en aceptar conexiones reales después de arrancar. Sin healthcheck, MLflow intentaría conectarse a Postgres antes de que esté listo y fallaría.
El flujo con healthchecks es:

```bash
postgres arranca
    → Docker ejecuta pg_isready cada 10s
    → cuando responde OK → marca postgres como "healthy"
        → pgbouncer arranca (depends_on: postgres healthy)
            → cuando pgbouncer responde OK → marca como "healthy"
                → mlflow, prefect, jupyterhub arrancan (depends_on: pgbouncer healthy)
```
Sin healthchecks ese orden no está garantizado y los servicios fallan al arrancar por conexión rechazada, luego Docker los reinicia solos — funciona eventualmente pero genera errores en los logs y puede corromper migraciones de base de datos si el ORM intenta crear tablas a medias.

## Entrar a los contenedores

Todos los comandos asumen que estás parado en la raíz del proyecto.

```bash
sudo docker compose ps
sudo docker compose logs -f

# General
sudo docker exec -it ds_postgres bash
sudo docker exec -it ds_postgres psql -U "$POSTGRES_USER" -d postgres
sudo docker exec -it ds_jupyterhub bash
sudo docker exec -it ds_minio sh
sudo docker exec -it ds_mlflow sh
sudo docker exec -it ds_prefect bash
sudo docker exec -it ds_streamlit sh
sudo docker inspect ds_postgres --format '{{json .Mounts}}'
sudo docker inspect ds_jupyterhub --format '{{json .Mounts}}'
```

### PostgreSQL

```bash
sudo docker exec -it ds_postgres bash
sudo docker compose exec postgres psql -U "$POSTGRES_USER" -d postgres
sudo docker exec -it ds_postgres psql -U "$POSTGRES_USER" -d postgres
sudo docker exec -it ds_postgres psql -U "$POSTGRES_USER" -d jupyterhub
```

Consultas útiles dentro de `psql`:

```sql
\l
\c jupyterhub
\dt
SELECT count(*) FROM users;
```

#### Pgbouncer
# 1. Generar el userlist.txt con tus credenciales reales
```bash
chmod +x pgbouncer/generate-config.sh
./pgbouncer/generate-config.sh
```

# 2. Verificar que se generó
```bash
cat pgbouncer/userlist.txt   # debe mostrar: "tu_usuario" "tu_password"
```

# 3. Levantar
```bash
sudo docker compose -f docker-compose.yml up -d
```

##### Crear una base de datos nueva desde PostgreSQL
```bash
<!-- ***************************************************** -->
sudo docker compose exec postgres psql -U "$POSTGRES_USER" -d postgres

CREATE DATABASE saacdata;
\l
\c saacdata
<!-- ***************************************************** -->
```

Nota: si escribes `CREATE DATABASE SAACDATA;` sin comillas, PostgreSQL realmente crea `saacdata` en minúsculas. Si quieres usar mayúsculas exactas, tendrías que crearla como `CREATE DATABASE "SAACDATA";` y luego conectarte con `\c "SAACDATA"`, pero no es recomendable para uso diario. Para salir `CTRL + D`.

Agregar datos a la base de datos
```bash
sudo docker compose exec postgres psql -U "$POSTGRES_USER" -d saacdata

CREATE TABLE otri (
    id BIGSERIAL PRIMARY KEY,
    nombre TEXT NOT NULL,
    creado_en TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

O ejecutar un script
```bash
<!-- ***************************************************** -->
sudo docker compose exec -T postgres psql -U "$POSTGRES_USER" -d saacdata < sql/create-db.sql
sudo docker compose exec -T postgres psql -U "$POSTGRES_USER" -d saacdata < sql/add-db.sql
# Ejecutar despues de add-db para resincronizar la secuencia de insert
sudo docker compose exec postgres psql -U "$POSTGRES_USER" -d saacdata -c "SELECT setval(pg_get_serial_sequence('\"OTRI\".\"T_OTRI_PI_ESTADOS\"', 'IDOTRIPIESTADOS'), (SELECT MAX(\"IDOTRIPIESTADOS\") FROM \"OTRI\".\"T_OTRI_PI_ESTADOS\"));"
<!-- ***************************************************** -->
```

### MinIO

```bash
sudo docker exec -it ds_minio sh
ls -lah /data
```

También puedes revisar el contenido desde la consola web en `http://SERVER_IP:9001`.

### JupyterHub

```bash
sudo docker exec -it ds_jupyterhub bash
ls -lah /srv/jupyterhub
ls -lah /home
env | sort
```

##### Un ".env"
Crearlo manualmente por seguridad no todos los usuarios pueden ver los archivos ocultos por seguridad como ".env"
```bash
touch RUTA/datascience/notebooks/USUARIOS/CARPETA/.env
nano RUTA/datascience/notebooks/USUARIOS/CARPETA/.env
cat RUTA/datascience/notebooks/USUARIOS/CARPETA/.env
ls -la RUTA/datascience/notebooks/USUARIOS/CARPETA/.env
```

### MLflow

```bash
sudo docker exec -it ds_mlflow sh
env | sort
```

### Prefect

```bash
sudo docker exec -it ds_prefect bash
prefect version
```

### Streamlit

```bash
sudo docker exec -it ds_streamlit sh
ls -lah /app
ls -lah /data/local
```

## Inspeccionar mounts y variables

```bash
sudo docker inspect ds_postgres
sudo docker inspect ds_jupyterhub
sudo docker inspect ds_minio
```

Si quieres ver solo los mounts:

```bash
sudo docker inspect ds_postgres --format '{{json .Mounts}}'
sudo docker inspect ds_jupyterhub --format '{{json .Mounts}}'
sudo docker inspect ds_minio --format '{{json .Mounts}}'
```

## JupyterHub usando PostgreSQL

JupyterHub quedó configurado para usar la base `jupyterhub` de PostgreSQL mediante la variable `JUPYTERHUB_DB_URL`. El archivo de cookies sigue persistiendo en `/srv/jupyterhub`, pero usuarios, tokens y estado interno pasan a Postgres.

Para aplicar el cambio:

```bash
sudo docker compose build jupyterhub
sudo docker compose up -d jupyterhub
sudo docker compose logs -f jupyterhub
```

Si quieres confirmar desde Postgres:

```bash
sudo docker exec -it ds_postgres psql -U "$POSTGRES_USER" -d jupyterhub -c "\dt"
```

Nota: si ya tenías usuarios en el archivo SQLite anterior, no se migran solos a Postgres. Ese archivo quedará como historial local hasta que decidas migrarlo o descartarlo.

## Crear usuario admin en JupyterHub

Con `NativeAuthenticator`, el flujo más simple es registrar el usuario desde `http://SERVER_IP:8000/hub/signup` usando el nombre definido en `JUPYTERHUB_ADMIN`.

Si además necesitas crear el usuario de sistema dentro del contenedor:

```bash
sudo docker exec -it ds_jupyterhub useradd -m -s /bin/bash admin
sudo docker exec -it ds_jupyterhub sh -c "echo 'admin:contrasenia123' | chpasswd"
sudo docker compose restart jupyterhub
```

## Ver si los puertos  estan ocupados en el server
```bash
sudo ss -tulpn | grep -E '8000|9001|5000|8501'
```

## Verificación de conectividad

```bash
curl -I http://localhost:8000
curl -I http://localhost:5000
curl -I http://localhost:4200/api/health
curl -I http://localhost:9001
```

Desde otra máquina Windows:

```powershell
Test-NetConnection -ComputerName 192.168.10.59 -Port 8000
Test-NetConnection -ComputerName 192.168.10.59 -Port 9001
Test-NetConnection -ComputerName 192.168.10.59 -Port 5000
Test-NetConnection -ComputerName 192.168.10.59 -Port 4200
```

Desde el mismo servidor, por ejemplo base:
```bash
nc -zv 192.168.254.25 50000
telnet 192.168.254.25 50000
nc -zv 192.168.254.87 50000
telnet 192.168.254.87 50000
```

Dentro del contenedor:
```bash
sudo docker exec -it n8n telnet 192.168.254.87 50000
```

Desde otro servidor:
```bash
nc -zv 192.168.254.25 50000
telnet 192.168.254.25 50000
nc -zv 192.168.254.87 50000
telnet 192.168.254.87 50000
nc -zv 192.168.10.59 8501
telnet 192.168.10.59 8501
nc -zv 192.168.10.59 9000
telnet 192.168.10.59 9000
```

## Cuándo necesitarías un proxy
Usa Nginx o Traefik si quieres exponer todo por 80/443, centralizar HTTPS o publicar una sola URL sin puertos explícitos.

## Agregar Bucket a MinIo
```bash
sudo docker compose run --rm --entrypoint sh minio-setup -c "
  mc alias set myminio http://minio:9000 \$MINIO_ROOT_USER \$MINIO_ROOT_PASSWORD && \
  mc mb --ignore-existing myminio/download-files && \
  mc anonymous set download myminio/download-files && \
  echo 'Bucket creado y politica aplicada correctamente'
"
```

Y para descargar seria algo como:
```bash
http://192.168.10.59:9000/download-files/cv_th/tmp_cv_0922663208_format_A.pdf
```
