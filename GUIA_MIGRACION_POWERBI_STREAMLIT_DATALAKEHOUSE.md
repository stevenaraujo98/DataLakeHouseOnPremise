# Guía de trabajo para migrar proyectos de Power BI a Streamlit con MinIO, DuckDB y Prefect

## 1. Objetivo

Este documento define una forma estándar de desarrollar y migrar proyectos de Business Intelligence desde Power BI hacia una arquitectura basada en:

- **JupyterHub** para exploración, desarrollo y prototipado.
- **MinIO** como almacenamiento del Data Lakehouse.
- **Parquet** como formato principal para las capas Silver y Gold.
- **DuckDB** como motor analítico OLAP y capa de consulta.
- **Prefect** para automatizar y programar los pipelines.
- **Streamlit** para construir y publicar los dashboards.
- **PostgreSQL** para datos operacionales o casos que necesiten alta concurrencia de escritura/lectura relacional.
- **Traefik** para publicar los dashboards Streamlit por proyecto.

El objetivo principal es sustituir gradualmente las responsabilidades que actualmente resuelve Power BI, manteniendo una arquitectura desacoplada, reproducible y mantenible.

---

# 2. Principio arquitectónico

La arquitectura debe seguir esta separación de responsabilidades:

> **MinIO/Parquet almacena los datos. DuckDB consulta y modela analíticamente los datos. Prefect construye y actualiza los datos. Streamlit presenta los datos.**

No se recomienda utilizar un único archivo `.duckdb` almacenado en MinIO como fuente principal del dashboard.

La capa Gold debe mantenerse principalmente como archivos **Parquet**.

DuckDB debe utilizarse como motor de consulta sobre esos archivos.

---

# 3. Arquitectura general

```text
                         FUENTES DE DATOS
                               │
                               ▼
                    ┌─────────────────────┐
                    │   Ingesta / Raw     │
                    │ Python / APIs / SQL │
                    └──────────┬──────────┘
                               │
                               ▼
                    MinIO - raw-data
                    └── bronze/
                               │
                               ▼
                    ┌─────────────────────┐
                    │ Limpieza / Silver   │
                    │ Pandas / Polars     │
                    │ DuckDB              │
                    └──────────┬──────────┘
                               │
                               ▼
                  MinIO - processed-data
                  └── silver/
                               │
                               ▼
                    ┌─────────────────────┐
                    │ Modelo BI / Gold    │
                    │ DuckDB / SQL        │
                    │ Modelo estrella     │
                    └──────────┬──────────┘
                               │
                               ▼
                  MinIO - processed-data
                  └── gold/
                      ├── fact/
                      ├── dim/
                      └── marts/
                               │
                               ▼
                          DuckDB
                     motor analítico
                               │
                               ▼
                         Streamlit
                    KPIs / filtros / gráficos
```

---

# 4. Equivalencia con Power BI

Al migrar un proyecto debe identificarse qué responsabilidad de Power BI se está reemplazando.

| Power BI | Arquitectura propuesta |
|---|---|
| Power Query | Jupyter / Python / Pandas / Polars / DuckDB |
| Importación de fuentes | Notebook/flow de ingesta |
| Relaciones entre tablas | Modelo estrella + JOIN SQL |
| Dataset / modelo tabular | Gold en MinIO |
| VertiPaq | DuckDB |
| Columnas calculadas | Silver o Gold |
| DAX | SQL reutilizable / capa semántica |
| Medidas | Queries SQL / vistas / funciones |
| Refresh | Prefect |
| Visualizaciones | Streamlit |
| Filtros / slicers | Widgets de Streamlit |
| Power BI Service | Streamlit + Traefik |
| Seguridad por proyecto | Login propio de cada dashboard |

---

# 5. Capas del Data Lakehouse

## 5.1 Bronze

La capa Bronze debe contener el dato tal como llega desde la fuente.

Ruta recomendada:

```text
s3://raw-data/bronze/<proyecto>/<fuente>/<fecha>/
```

Ejemplo:

```text
raw-data/
└── bronze/
    └── planificacion-academica/
        ├── estudiantes/
        ├── materias/
        ├── docentes/
        └── matriculas/
```

### Reglas

- No aplicar lógica de negocio compleja.
- Mantener una copia reproducible del dato original.
- Registrar fecha o lote de extracción cuando sea necesario.
- Evitar modificar archivos históricos.
- Preferir formatos como Parquet cuando la fuente lo permita.
- CSV/JSON pueden mantenerse cuando constituyen el formato original.

---

# 6. Notebook 01 - Ingesta de datos

Nombre recomendado:

```text
01_raw_data.ipynb
```

Responsabilidades:

1. Conectarse a la fuente.
2. Descargar los datos.
3. Realizar validaciones mínimas.
4. Registrar cantidad de filas.
5. Registrar fecha de extracción.
6. Guardar en `raw-data/bronze`.
7. No implementar reglas analíticas del dashboard.

Ejemplo conceptual:

```python
import pandas as pd

df = obtener_datos_desde_fuente()

print(df.shape)
print(df.dtypes)
print(df.head())

subir_dataframe_archivo(
    s3,
    df,
    bucket="raw-data",
    key="bronze/proyecto/matriculas/matriculas.parquet"
)
```

---

# 7. Capa Silver

Silver contiene datos:

- limpios;
- tipados;
- normalizados;
- deduplicados;
- enriquecidos cuando sea necesario;
- preparados para construir modelos analíticos.

Ejemplo:

```text
processed-data/
└── silver/
    └── planificacion-academica/
        ├── estudiantes.parquet
        ├── materias.parquet
        ├── docentes.parquet
        ├── carreras.parquet
        ├── periodos.parquet
        └── matriculas.parquet
```

---

# 8. Notebook 02 - Procesamiento Silver

Nombre recomendado:

```text
02_silver.ipynb
```

Responsabilidades:

1. Leer Bronze.
2. Corregir tipos.
3. Eliminar duplicados.
4. Manejar nulos.
5. Normalizar nombres.
6. Homologar identificadores.
7. Crear campos derivados básicos.
8. Validar claves.
9. Guardar resultados en Silver.

Ejemplo:

```python
df["id_estudiante"] = df["id_estudiante"].astype("string")
df["fecha"] = pd.to_datetime(df["fecha"])
df = df.drop_duplicates()
```

### Qué NO debería hacerse todavía

Evitar crear en Silver:

- KPIs finales;
- agregaciones específicas de una pantalla;
- cálculos exclusivos de un gráfico;
- tablas demasiado desnormalizadas para un único dashboard.

Silver debe seguir siendo una capa reutilizable.

---

# 9. Capa Gold

Gold es la capa preparada específicamente para análisis, reporting y BI.

Ruta recomendada:

```text
processed-data/
└── gold/
    └── <proyecto>/
```

Se recomienda dividirla en tres áreas:

```text
gold/
└── proyecto/
    ├── fact/
    ├── dim/
    └── marts/
```

---

# 10. Modelo dimensional

Las relaciones que anteriormente se definían en Power BI deben representarse explícitamente mediante un modelo dimensional.

Ejemplo:

```text
                       DIM_ESTUDIANTE
                             │
                             │
DIM_PERIODO ────── FACT_MATRICULA ───── DIM_MATERIA
                             │
                             │
                         DIM_CARRERA
                             │
                             │
                         DIM_DOCENTE
```

Estructura física:

```text
gold/
└── proyecto/
    ├── fact/
    │   └── fact_matricula.parquet
    │
    ├── dim/
    │   ├── dim_estudiante.parquet
    │   ├── dim_materia.parquet
    │   ├── dim_carrera.parquet
    │   ├── dim_periodo.parquet
    │   └── dim_docente.parquet
    │
    └── marts/
```

---

# 11. Tablas de hechos

Las tablas `fact_*` contienen eventos, transacciones o medidas.

Ejemplos:

```text
fact_matricula
fact_inscripcion
fact_asistencia
fact_evaluacion
fact_planificacion_docente
```

Ejemplo conceptual de `fact_matricula`:

| id_estudiante | id_materia | id_periodo | id_carrera | estado | nota |
|---|---|---|---|---|---|

---

# 12. Dimensiones

Las tablas `dim_*` contienen atributos descriptivos.

Ejemplos:

```text
dim_estudiante
dim_materia
dim_carrera
dim_periodo
dim_docente
```

Ejemplo:

```text
dim_materia

id_materia
codigo
nombre
nivel
creditos
departamento
```

---

# 13. Data Marts

Los `marts` contienen datos preparados para necesidades frecuentes del dashboard.

Ejemplos:

```text
marts/
├── demanda_materias.parquet
├── matriculas_por_periodo.parquet
├── carga_docentes.parquet
├── riesgo_reprobacion.parquet
└── kpis_academicos.parquet
```

Un Data Mart debe crearse cuando:

- la consulta se ejecuta constantemente;
- requiere joins o agregaciones pesadas;
- alimenta varios gráficos;
- representa una métrica de negocio estable;
- conviene calcularla durante el pipeline y no cada vez que entra un usuario.

---

# 14. Notebook 03 - Construcción Gold

Nombre recomendado:

```text
03_gold.ipynb
```

Responsabilidades:

1. Leer Silver.
2. Construir dimensiones.
3. Construir hechos.
4. Validar relaciones.
5. Crear Data Marts.
6. Definir métricas de negocio.
7. Escribir Parquet en Gold.

Ejemplo conceptual con DuckDB:

```python
import duckdb

con = duckdb.connect()

df_resultado = con.sql("""
    SELECT
        id_periodo,
        id_materia,
        COUNT(DISTINCT id_estudiante) AS estudiantes
    FROM matriculas
    GROUP BY
        id_periodo,
        id_materia
""").df()
```

---

# 15. Por qué Gold debe ser Parquet

Parquet ofrece:

- almacenamiento columnar;
- buena compresión;
- lectura selectiva de columnas;
- mejor rendimiento analítico que CSV;
- compatibilidad con DuckDB;
- compatibilidad con Pandas y Polars;
- facilidad para almacenar datasets en MinIO;
- independencia respecto de un motor específico.

Por esta razón:

```text
Gold = Parquet
```

y no:

```text
Gold = un archivo .duckdb
```

---

# 16. Rol de DuckDB

DuckDB debe actuar principalmente como:

- motor OLAP;
- motor de JOIN;
- motor de agregaciones;
- motor SQL;
- lector de Parquet;
- capa de consulta para Streamlit;
- herramienta de procesamiento durante Silver/Gold.

No debe considerarse obligatoriamente como la fuente física permanente de Gold.

---

# 17. DuckDB en Streamlit

Patrón recomendado:

```python
import duckdb

con = duckdb.connect(":memory:")
```

El dashboard crea una conexión local y consulta Gold.

Conceptualmente:

```sql
SELECT
    periodo,
    carrera,
    COUNT(*) AS total
FROM read_parquet(
    's3://processed-data/gold/proyecto/...'
)
GROUP BY periodo, carrera;
```

---

# 18. Capa semántica

Power BI permite crear:

- relaciones;
- medidas;
- columnas;
- DAX;
- contexto de filtros.

Cuando se utiliza Streamlit, esta capa debe diseñarse explícitamente.

Se recomienda crear una carpeta:

```text
semantic/
```

Ejemplo:

```text
dashboards/
└── proyecto/
    ├── app.py
    ├── semantic/
    │   ├── model.sql
    │   ├── kpis.sql
    │   ├── estudiantes.sql
    │   └── materias.sql
    └── pages/
```

---

# 19. Archivo model.sql

`model.sql` puede registrar las tablas lógicas del modelo.

Ejemplo:

```sql
CREATE VIEW fact_matricula AS
SELECT *
FROM read_parquet(
    's3://processed-data/gold/proyecto/fact/fact_matricula.parquet'
);

CREATE VIEW dim_estudiante AS
SELECT *
FROM read_parquet(
    's3://processed-data/gold/proyecto/dim/dim_estudiante.parquet'
);

CREATE VIEW dim_materia AS
SELECT *
FROM read_parquet(
    's3://processed-data/gold/proyecto/dim/dim_materia.parquet'
);
```

Esto evita repetir rutas S3 en todas las consultas.

---

# 20. Sustitución de relaciones de Power BI

Una relación en Power BI:

```text
fact_matricula[id_materia]
        ↓
dim_materia[id_materia]
```

se convierte en SQL:

```sql
SELECT
    f.*,
    m.nombre
FROM fact_matricula f
LEFT JOIN dim_materia m
    ON f.id_materia = m.id_materia;
```

---

# 21. Sustitución de DAX

Ejemplo Power BI:

```text
Total Estudiantes =
DISTINCTCOUNT(Matricula[id_estudiante])
```

Equivalente SQL:

```sql
SELECT
    COUNT(DISTINCT id_estudiante) AS total_estudiantes
FROM fact_matricula;
```

Otro ejemplo:

```sql
SELECT
    id_periodo,
    COUNT(DISTINCT id_estudiante) AS total_estudiantes
FROM fact_matricula
GROUP BY id_periodo;
```

La regla recomendada es:

```text
DAX reutilizable
        ↓
SQL reutilizable
        ↓
semantic/
```

---

# 22. Evitar SQL de negocio dentro de app.py

No se recomienda:

```python
# app.py
df = con.sql("SELECT ... JOIN ... GROUP BY ...").df()
```

si esa consulta representa lógica importante de negocio.

Es preferible:

```text
semantic/
└── demanda_materias.sql
```

y desde Python ejecutar ese archivo.

Esto mejora:

- mantenimiento;
- pruebas;
- reutilización;
- control de versiones;
- migraciones;
- revisión de código.

---

# 23. Estructura recomendada para un dashboard

```text
dashboards/
└── proyecto/
    ├── app.py
    ├── Dockerfile
    ├── requirements.txt
    ├── config.yaml
    │
    ├── data/
    │   ├── connection.py
    │   ├── repository.py
    │   └── queries.py
    │
    ├── semantic/
    │   ├── model.sql
    │   ├── kpis.sql
    │   ├── demanda.sql
    │   └── docentes.sql
    │
    ├── components/
    │   ├── filters.py
    │   ├── cards.py
    │   ├── charts.py
    │   └── tables.py
    │
    ├── pages/
    │   ├── 01_resumen.py
    │   ├── 02_demanda.py
    │   ├── 03_docentes.py
    │   └── 04_estudiantes.py
    │
    └── utils/
        └── helpers.py
```

---

# 24. Separación de responsabilidades en Streamlit

## `app.py`

Debe encargarse principalmente de:

- configuración inicial;
- autenticación;
- navegación;
- layout principal.

## `data/`

Debe encargarse de:

- DuckDB;
- MinIO;
- ejecución de queries;
- caché de datos.

## `semantic/`

Debe contener:

- SQL del modelo;
- KPIs;
- lógica analítica;
- vistas.

## `components/`

Debe contener:

- gráficos reutilizables;
- tarjetas KPI;
- filtros;
- tablas.

## `pages/`

Debe contener:

- pantallas de negocio.

---

# 25. Prototipo antes de Streamlit

Se recomienda utilizar un notebook adicional:

```text
04_dashboard_prototype.ipynb
```

En este notebook deben validarse:

- queries;
- KPIs;
- filtros;
- gráficos;
- rendimiento;
- resultados contra Power BI.

Una vez validado:

```text
Notebook
   ↓
SQL / Python reusable
   ↓
Streamlit
```

---

# 26. Flujo completo durante desarrollo

```text
01_raw_data.ipynb
        │
        ▼
raw-data/bronze
        │
        ▼
02_silver.ipynb
        │
        ▼
processed-data/silver
        │
        ▼
03_gold.ipynb
        │
        ▼
processed-data/gold
        │
        ▼
04_dashboard_prototype.ipynb
        │
        ▼
Streamlit
```

---

# 27. Paso de notebooks a producción

Los notebooks sirven para:

- exploración;
- pruebas;
- desarrollo;
- debugging.

No deberían ser el mecanismo final de producción.

Cuando el pipeline sea estable:

```text
.ipynb
   ↓
.py
   ↓
@task
   ↓
@flow
   ↓
Prefect Deployment
   ↓
Schedule
```

---

# 28. Estructura recomendada de flows

Ejemplo:

```text
proyecto/
├── notebooks/
│   ├── 01_raw_data.ipynb
│   ├── 02_silver.ipynb
│   ├── 03_gold.ipynb
│   └── 04_dashboard_prototype.ipynb
│
└── flows/
    ├── ingest_raw.py
    ├── build_silver.py
    ├── build_gold.py
    └── pipeline.py
```

Dependiendo del proyecto también puede utilizarse un único flow principal.

---

# 29. Flow completo

Ejemplo conceptual:

```python
from prefect import flow

@flow(name="pipeline-dashboard")
def pipeline_dashboard():
    ingest_raw()
    build_silver()
    build_gold()

if __name__ == "__main__":
    pipeline_dashboard()
```

---

# 30. Work Pool de Prefect

Para procesamiento que alimenta dashboards debe usarse preferentemente:

```text
dashboards
```

Ejemplo:

```bash
prefect deploy pipeline.py:pipeline_dashboard \
    --name "pipeline-dashboard-proyecto" \
    --pool dashboards \
    --tag proyecto
```

Los pools deben elegirse por tipo de carga, no creando un pool diferente para cada proyecto.

---

# 31. Programación

Un patrón típico puede ser:

```text
01:00    Ingesta
01:30    Silver
02:00    Gold
07:00    Usuarios consultan dashboard
```

O ejecutar todo como un único flow:

```text
02:00
    ↓
Raw
    ↓
Silver
    ↓
Gold
```

Siempre configurar Prefect con:

```text
America/Guayaquil
```

cuando los schedules correspondan a hora Ecuador.

---

# 32. Streamlit no debe construir Silver/Gold

Evitar:

```text
Usuario abre dashboard
        ↓
Streamlit descarga Raw
        ↓
limpia datos
        ↓
hace joins
        ↓
calcula 40 KPIs
        ↓
muestra dashboard
```

Patrón correcto:

```text
Prefect
   ↓
calcula previamente
   ↓
Gold
   ↓
Streamlit consulta
```

Esto reduce:

- tiempo de carga;
- consumo de CPU;
- errores;
- duplicación de lógica;
- diferencias entre usuarios.

---

# 33. Uso de caché en Streamlit

Para datos relativamente estables:

```python
import streamlit as st

@st.cache_data(ttl=600)
def obtener_datos():
    ...
```

Esto evita ejecutar repetidamente la misma consulta.

No obstante, la caché no reemplaza la necesidad de construir correctamente Gold.

---

# 34. Cuándo utilizar PostgreSQL

PostgreSQL debe utilizarse cuando el proyecto necesita:

- CRUD;
- formularios;
- configuración persistente;
- escritura concurrente;
- datos transaccionales;
- estado del aplicativo;
- muchas aplicaciones accediendo simultáneamente al mismo modelo operacional.

Ejemplo:

```text
Streamlit
   ↓
Formulario
   ↓
PostgreSQL
```

Para BI histórico/analítico:

```text
Streamlit
   ↓
DuckDB
   ↓
Parquet / MinIO
```

---

# 35. Cuándo utilizar DuckDB local persistente

Puede utilizarse un `.duckdb` local cuando:

- existe un solo proceso consumidor;
- se necesita máxima velocidad local;
- el archivo está en SSD;
- no se necesita que MinIO sea la fuente principal;
- se entiende claramente el modelo de concurrencia.

No debería convertirse en la opción predeterminada para todos los proyectos.

---

# 36. Cuándo utilizar Data Marts

Crear un Mart cuando un cálculo:

- requiere mucho procesamiento;
- se consulta frecuentemente;
- cambia solo cuando llega nueva información;
- alimenta múltiples gráficos;
- tiene una definición de negocio estable.

Ejemplo:

```text
marts/demanda_materia.parquet
```

Columnas:

```text
periodo
carrera
materia
estudiantes
cupos
diferencia
porcentaje_ocupacion
```

---

# 37. Diseño de KPIs

Cada KPI debe tener:

1. nombre;
2. definición;
3. fórmula;
4. granularidad;
5. filtros aplicables;
6. fuente;
7. SQL asociado.

Ejemplo:

```text
KPI:
Estudiantes matriculados

Definición:
Número de estudiantes únicos matriculados.

Granularidad:
Periodo / carrera / materia.

SQL:
COUNT(DISTINCT id_estudiante)
```

Esto evita que dos dashboards calculen una misma métrica de forma diferente.

---

# 38. Catálogo semántico recomendado

Puede mantenerse un archivo:

```text
semantic/README.md
```

Ejemplo:

```markdown
# KPIs

## total_estudiantes

COUNT(DISTINCT id_estudiante)

Fuente:
fact_matricula

## tasa_reprobacion

reprobados / total_estudiantes
```

---

# 39. Migración de un proyecto Power BI existente

La migración no debería comenzar copiando gráficos.

Debe hacerse en este orden.

## Paso 1 - Inventariar fuentes

Registrar:

- bases de datos;
- Excel;
- CSV;
- APIs;
- SharePoint;
- archivos externos.

## Paso 2 - Inventariar Power Query

Identificar:

- joins;
- filtros;
- reemplazos;
- columnas derivadas;
- transformaciones;
- limpieza.

Clasificar cada operación como:

```text
Bronze
Silver
Gold
```

## Paso 3 - Inventariar modelo Power BI

Registrar:

- tablas;
- relaciones;
- cardinalidad;
- claves;
- dimensiones;
- hechos;
- tablas puente.

## Paso 4 - Inventariar DAX

Clasificar:

```text
Columnas calculadas
Medidas simples
Medidas complejas
Time Intelligence
KPIs
```

## Paso 5 - Inventariar visualizaciones

Por cada página Power BI:

- filtros;
- KPIs;
- tablas;
- gráficos;
- drilldowns;
- tooltips;
- navegación.

---

# 40. Matriz de migración

Crear una tabla como:

| Power BI | Tipo | Destino |
|---|---|---|
| Query Matriculas | Power Query | Silver |
| Query Estudiantes | Power Query | Silver |
| Relación matrícula-materia | Relationship | Gold |
| Total estudiantes | DAX | semantic/kpis.sql |
| Demanda por materia | DAX | Mart |
| Gráfico barras | Visual | Streamlit |
| Segmentador periodo | Filter | Streamlit selectbox |

---

# 41. Construcción del nuevo pipeline

Orden recomendado:

```text
Fuentes
   ↓
Bronze
   ↓
Silver
   ↓
Gold
   ↓
Semantic SQL
   ↓
Streamlit
```

No empezar construyendo Streamlit antes de estabilizar Gold.

---

# 42. Validación contra Power BI

Durante la migración mantener temporalmente ambos sistemas.

Comparar:

```text
Power BI
vs
Streamlit
```

Para:

- total general;
- KPIs;
- filtros;
- agrupaciones;
- periodos;
- carreras;
- materias;
- valores extremos.

---

# 43. Pruebas mínimas

Por cada tabla Gold validar:

```text
cantidad de filas
cantidad de columnas
tipos de datos
claves duplicadas
claves nulas
integridad entre fact y dim
rangos
fechas
```

Ejemplo SQL:

```sql
SELECT COUNT(*)
FROM fact_matricula;
```

Duplicados:

```sql
SELECT
    id_matricula,
    COUNT(*)
FROM fact_matricula
GROUP BY id_matricula
HAVING COUNT(*) > 1;
```

---

# 44. Validación de relaciones

Ejemplo:

```sql
SELECT COUNT(*)
FROM fact_matricula f
LEFT JOIN dim_materia m
    ON f.id_materia = m.id_materia
WHERE m.id_materia IS NULL;
```

Resultado esperado:

```text
0
```

salvo que el modelo de negocio permita claves huérfanas.

---

# 45. Validación de KPIs

Ejemplo:

```text
Power BI = 10.245 estudiantes
Streamlit/DuckDB = 10.245 estudiantes
```

Si existe diferencia:

1. revisar filtros;
2. revisar duplicados;
3. revisar relaciones;
4. revisar contexto DAX;
5. revisar granularidad;
6. revisar fechas.

---

# 46. Rendimiento

Antes de publicar:

- medir tiempo de cada query;
- identificar scans grandes;
- crear Marts cuando sea conveniente;
- evitar descargar datasets completos innecesariamente;
- seleccionar únicamente columnas necesarias;
- filtrar lo antes posible.

Evitar:

```sql
SELECT *
```

cuando solo se requieren pocas columnas.

---

# 47. Particionado

Cuando los datasets crezcan considerablemente puede utilizarse particionado por:

```text
año
periodo
fecha
unidad
```

Ejemplo:

```text
gold/
└── fact/
    └── matricula/
        ├── periodo=2025-1/
        ├── periodo=2025-2/
        └── periodo=2026-1/
```

No particionar demasiado pronto si el volumen aún es pequeño.

---

# 48. Convenciones de nombres

Recomendación:

```text
snake_case
```

Ejemplos:

```text
id_estudiante
fecha_matricula
nombre_carrera
total_estudiantes
```

Tablas:

```text
fact_matricula
dim_estudiante
mart_demanda_materia
```

---

# 49. Versionado

El código debe mantenerse en Git:

```text
flows/
dashboards/
semantic/
SQL
```

Los datos no deben guardarse en Git.

Datos runtime:

```text
/data/datascience/
```

Código:

```text
/data/DataLakeHouseOnPremise/
```

---

# 50. Flujo de trabajo del desarrollador

## Fase de exploración

```text
JupyterHub
    ↓
Notebook
```

## Fase de estabilización

```text
Notebook
    ↓
Python / SQL
```

## Fase de automatización

```text
Python
    ↓
Prefect
```

## Fase de presentación

```text
Gold
    ↓
DuckDB
    ↓
Streamlit
```

---

# 51. Flujo recomendado para cambios

Ejemplo: se solicita un KPI nuevo.

No modificar inmediatamente `app.py`.

Proceso:

```text
1. Definir KPI.
2. Determinar fuente.
3. Determinar granularidad.
4. Determinar si pertenece a Gold, Mart o semantic SQL.
5. Implementar.
6. Validar en notebook.
7. Actualizar flow si corresponde.
8. Ejecutar pipeline.
9. Validar resultado.
10. Agregar visualización Streamlit.
```

---

# 52. Qué lógica pertenece a cada capa

## Bronze

```text
Dato original
```

## Silver

```text
Limpieza
Normalización
Tipado
Homologación
Enriquecimiento básico
```

## Gold

```text
Modelo estrella
Hechos
Dimensiones
Agregaciones
Data Marts
```

## Semantic

```text
KPIs
Métricas
JOIN reutilizables
Consultas analíticas
```

## Streamlit

```text
UI
Filtros
Gráficos
Tablas
Interacciones
```

---

# 53. Qué evitar

## No hacer

```text
Raw → Streamlit
```

## No hacer

```text
Streamlit → transformar millones de registros en cada visita
```

## No hacer

```text
DAX → copiar directamente como lógica Python dispersa
```

## No hacer

```text
Un .duckdb remoto como única fuente Gold para todos los proyectos
```

## No hacer

```text
Una única app Streamlit gigantesca para todos los clientes
```

## No hacer

```text
Duplicar el mismo KPI en varios archivos con fórmulas diferentes
```

---

# 54. Arquitectura de dashboards del stack

El stack actualmente utiliza un contenedor Streamlit por proyecto.

Conceptualmente:

```text
Traefik
   │
   ├── /proyecto-a
   │       ↓
   │   Streamlit A
   │
   ├── /proyecto-b
   │       ↓
   │   Streamlit B
   │
   └── /proyecto-c
           ↓
       Streamlit C
```

Cada dashboard puede:

- tener autenticación propia;
- tener roles;
- evolucionar independientemente;
- usar el Gold específico del proyecto.

---

# 55. Separación por proyecto en MinIO

Ejemplo:

```text
processed-data/
├── silver/
│   ├── proyecto-a/
│   ├── proyecto-b/
│   └── proyecto-c/
│
└── gold/
    ├── proyecto-a/
    ├── proyecto-b/
    └── proyecto-c/
```

---

# 56. Proyecto ejemplo completo

```text
proyecto-planificacion/
│
├── notebooks/
│   ├── 01_raw_data.ipynb
│   ├── 02_silver.ipynb
│   ├── 03_gold.ipynb
│   └── 04_dashboard_prototype.ipynb
│
├── flows/
│   └── pipeline.py
│
└── dashboard/
    ├── app.py
    ├── data/
    ├── semantic/
    ├── components/
    └── pages/
```

MinIO:

```text
raw-data/
└── bronze/
    └── proyecto-planificacion/

processed-data/
├── silver/
│   └── proyecto-planificacion/
│
└── gold/
    └── proyecto-planificacion/
        ├── fact/
        ├── dim/
        └── marts/
```

---

# 57. Estrategia de migración gradual

No es necesario migrar todos los dashboards al mismo tiempo.

Recomendación:

## Etapa 1

Seleccionar un dashboard:

- conocido;
- de complejidad media;
- con usuarios internos;
- con métricas bien entendidas.

## Etapa 2

Migrar:

```text
Power Query
    ↓
Silver
```

## Etapa 3

Migrar:

```text
Relationships
    ↓
Gold
```

## Etapa 4

Migrar:

```text
DAX
    ↓
Semantic SQL
```

## Etapa 5

Migrar:

```text
Visualizaciones
    ↓
Streamlit
```

## Etapa 6

Validar en paralelo.

## Etapa 7

Automatizar con Prefect.

## Etapa 8

Publicar.

---

# 58. Checklist de migración

## Datos

- [ ] Fuentes identificadas.
- [ ] Bronze implementado.
- [ ] Silver implementado.
- [ ] Gold implementado.
- [ ] Parquet utilizado.
- [ ] Validaciones de calidad implementadas.

## Modelo

- [ ] Hechos identificados.
- [ ] Dimensiones identificadas.
- [ ] Relaciones documentadas.
- [ ] Claves verificadas.
- [ ] Marts identificados.

## Métricas

- [ ] Medidas DAX inventariadas.
- [ ] KPIs documentados.
- [ ] SQL equivalente implementado.
- [ ] Resultados comparados con Power BI.

## Automatización

- [ ] Notebook convertido a flow.
- [ ] Deployment creado.
- [ ] Work pool correcto.
- [ ] Schedule configurado.
- [ ] Timezone configurado.

## Streamlit

- [ ] Dashboard separado por proyecto.
- [ ] Autenticación configurada.
- [ ] Queries fuera de `app.py`.
- [ ] Componentes reutilizables.
- [ ] Caché cuando aplica.
- [ ] Pruebas de rendimiento.

## Producción

- [ ] Power BI y Streamlit comparados.
- [ ] KPIs coinciden.
- [ ] Logs de Prefect revisados.
- [ ] Pipeline probado manualmente.
- [ ] Dashboard probado con usuarios.
- [ ] Documentación actualizada.

---

# 59. Decisión tecnológica recomendada

Para los proyectos BI de esta plataforma:

```text
ALMACENAMIENTO
MinIO + Parquet

PROCESAMIENTO
Pandas / Polars / DuckDB

ORQUESTACIÓN
Prefect

MODELO ANALÍTICO
Modelo estrella

MOTOR OLAP
DuckDB

SEMÁNTICA
SQL versionado

VISUALIZACIÓN
Streamlit

DATOS OPERACIONALES
PostgreSQL

DESPLIEGUE
Docker + Traefik
```

---

# 60. Flujo final objetivo

```text
                      ┌──────────────────┐
                      │ Fuentes externas │
                      └────────┬─────────┘
                               │
                               ▼
                        Prefect / Python
                               │
                               ▼
                    ┌─────────────────────┐
                    │       BRONZE        │
                    │ MinIO / raw-data    │
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │       SILVER        │
                    │ Parquet / MinIO     │
                    └──────────┬──────────┘
                               │
                          DuckDB/Polars
                               │
                               ▼
                    ┌─────────────────────┐
                    │        GOLD         │
                    │ fact / dim / marts  │
                    │ Parquet / MinIO     │
                    └──────────┬──────────┘
                               │
                               ▼
                         ┌───────────┐
                         │  DuckDB   │
                         │  OLAP SQL │
                         └─────┬─────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │ Semantic SQL Layer  │
                    │ KPI / Views / Marts │
                    └──────────┬──────────┘
                               │
                               ▼
                         ┌───────────┐
                         │ Streamlit │
                         └─────┬─────┘
                               │
                               ▼
                            Usuario
```

---

# 61. Principios que deben mantenerse

1. **El dashboard no transforma Raw.**
2. **Silver debe ser reutilizable.**
3. **Gold debe estar orientado al consumo analítico.**
4. **Gold se almacena preferentemente como Parquet.**
5. **DuckDB es un motor analítico, no necesariamente el almacenamiento Gold.**
6. **La lógica de negocio no debe quedar dispersa en Streamlit.**
7. **Los KPIs deben tener una única definición.**
8. **Prefect debe encargarse del refresh.**
9. **Los notebooks son para desarrollo, no para ejecución programada final.**
10. **Cada proyecto Streamlit debe mantenerse aislado.**
11. **PostgreSQL debe reservarse para necesidades relacionales/operacionales donde aporte valor.**
12. **Antes de retirar Power BI, los resultados deben compararse y validarse.**

---

# 62. Evolución futura

Cuando existan varios proyectos con modelos Gold similares y empiece a repetirse mucho SQL, puede evaluarse incorporar una herramienta como **dbt** para formalizar:

- dependencias entre modelos;
- tests;
- documentación;
- lineage;
- transformación SQL;
- construcción de modelos Gold.

No se considera obligatorio en la primera etapa.

La prioridad inicial debe ser estabilizar:

```text
MinIO
   +
Parquet
   +
Prefect
   +
DuckDB
   +
Streamlit
```

---

# 63. Referencias internas del proyecto

Esta guía debe utilizarse junto con la documentación existente del Data Lakehouse:

- `README.md`
- `AGENTS.md`
- `PREFECT_JUPYTER_GUIDE.md`
- `STREAMLIT_GUIDE.md`
- `MLFLOW_GUIDE.md`
- `ADITONAL.md`

Especialmente:

- `AGENTS.md` para estructura del stack, buckets, work pools y persistencia.
- `PREFECT_JUPYTER_GUIDE.md` para el proceso notebook → flow → deployment → schedule.
- `STREAMLIT_GUIDE.md` para crear y publicar un dashboard por proyecto.
- `README.md` para la arquitectura general del Data Lakehouse.

---

# 64. Resumen operativo

Para un proyecto nuevo:

```text
1. Crear proyecto.
2. Desarrollar 01_raw_data.ipynb.
3. Guardar Bronze.
4. Desarrollar 02_silver.ipynb.
5. Guardar Silver en Parquet.
6. Diseñar modelo estrella.
7. Desarrollar 03_gold.ipynb.
8. Crear fact, dim y marts.
9. Guardar Gold en Parquet.
10. Probar consultas con DuckDB.
11. Crear semantic SQL.
12. Validar KPIs.
13. Crear 04_dashboard_prototype.ipynb.
14. Comparar resultados con Power BI.
15. Crear Streamlit.
16. Separar data, semantic, components y pages.
17. Convertir los notebooks productivos a flows.
18. Deployar los flows en Prefect.
19. Utilizar el pool dashboards.
20. Configurar schedule America/Guayaquil.
21. Ejecutar pipeline completo.
22. Validar Gold.
23. Publicar Streamlit mediante Traefik.
24. Validar autenticación.
25. Comparar nuevamente Power BI vs Streamlit.
26. Pasar a producción.
```

Este flujo debe convertirse en el estándar de desarrollo de nuevos proyectos BI y en la base para migrar progresivamente los dashboards existentes de Power BI.
