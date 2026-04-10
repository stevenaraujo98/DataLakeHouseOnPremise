# Operación adicional

## Entrar a los contenedores

Todos los comandos asumen que estás parado en la raíz del proyecto.

```bash
docker compose ps
docker compose logs -f

# General
docker exec -it ds_postgres bash
docker exec -it ds_postgres psql -U "$POSTGRES_USER" -d postgres
docker exec -it ds_jupyterhub bash
docker exec -it ds_minio sh
docker exec -it ds_mlflow sh
docker exec -it ds_prefect bash
docker exec -it ds_streamlit sh
docker inspect ds_postgres --format '{{json .Mounts}}'
docker inspect ds_jupyterhub --format '{{json .Mounts}}'
```



### PostgreSQL

```bash
docker exec -it ds_postgres bash
docker exec -it ds_postgres psql -U "$POSTGRES_USER" -d postgres
docker exec -it ds_postgres psql -U "$POSTGRES_USER" -d jupyterhub
```

Consultas útiles dentro de `psql`:

```sql
\l
\c jupyterhub
\dt
SELECT count(*) FROM users;
```

### MinIO

```bash
docker exec -it ds_minio sh
ls -lah /data
```

También puedes revisar el contenido desde la consola web en `http://SERVER_IP:9001`.

### JupyterHub

```bash
docker exec -it ds_jupyterhub bash
ls -lah /srv/jupyterhub
ls -lah /home
env | sort
```

### MLflow

```bash
docker exec -it ds_mlflow sh
env | sort
```

### Prefect

```bash
docker exec -it ds_prefect bash
prefect version
```

### Streamlit

```bash
docker exec -it ds_streamlit sh
ls -lah /app
ls -lah /data/local
```

## Inspeccionar mounts y variables

```bash
docker inspect ds_postgres
docker inspect ds_jupyterhub
docker inspect ds_minio
```

Si quieres ver solo los mounts:

```bash
docker inspect ds_postgres --format '{{json .Mounts}}'
docker inspect ds_jupyterhub --format '{{json .Mounts}}'
docker inspect ds_minio --format '{{json .Mounts}}'
```

## JupyterHub usando PostgreSQL

JupyterHub quedó configurado para usar la base `jupyterhub` de PostgreSQL mediante la variable `JUPYTERHUB_DB_URL`. El archivo de cookies sigue persistiendo en `/srv/jupyterhub`, pero usuarios, tokens y estado interno pasan a Postgres.

Para aplicar el cambio:

```bash
docker compose build jupyterhub
docker compose up -d jupyterhub
docker compose logs -f jupyterhub
```

Si quieres confirmar desde Postgres:

```bash
docker exec -it ds_postgres psql -U "$POSTGRES_USER" -d jupyterhub -c "\dt"
```

Nota: si ya tenías usuarios en el archivo SQLite anterior, no se migran solos a Postgres. Ese archivo quedará como historial local hasta que decidas migrarlo o descartarlo.

## Crear usuario admin en JupyterHub

Con `NativeAuthenticator`, el flujo más simple es registrar el usuario desde `http://SERVER_IP:8000/hub/signup` usando el nombre definido en `JUPYTERHUB_ADMIN`.

Si además necesitas crear el usuario de sistema dentro del contenedor:

```bash
docker exec -it ds_jupyterhub useradd -m -s /bin/bash admin
docker exec -it ds_jupyterhub sh -c "echo 'admin:contrasenia123' | chpasswd"
docker compose restart jupyterhub
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

## Cuándo necesitarías un proxy

Usa Nginx o Traefik si quieres exponer todo por 80/443, centralizar HTTPS o publicar una sola URL sin puertos explícitos.
