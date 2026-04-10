# Operación adicional

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

## Cuándo necesitarías un proxy

Usa Nginx o Traefik si quieres exponer todo por 80/443, centralizar HTTPS o publicar una sola URL sin puertos explícitos.
