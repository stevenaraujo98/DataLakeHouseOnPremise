# Canvas · Almacenamiento

Réplica en Streamlit de las dos pestañas de Power BI de referencia:

- **Capacidad y uso**: cursos, GB asignados, GB utilizados, indicador semicircular con marca al 80 %, detalle con estados y descarga CSV.
- **Distribución por consumo**: tres paneles ordenados por porcentaje, con categorías excluyentes `<80`, `80–95` y `>95`. Las barras mantienen el porcentaje real aunque supere 100 %; cada panel utiliza una escala propia de al menos 100 %.

Filtros compartidos: solo E-Learning/todos, nivel, unidad, período/cohorte, tipo de materia y búsqueda por materia o ID. Sin selección en un filtro se incluyen todas sus opciones. El estado inicial muestra todos los cursos identificados como E-Learning, sin fijar los 11 cursos de la captura histórica.

## Contrato de datos

Lee exactamente las cuatro rutas del notebook `notebooks/4_dashboard_canvas.ipynb`, con boto3 y Polars, sin consultas a los sistemas de origen:

| Archivo bajo `s3://processed-data/gold/PowerBI/Canvas/` | Uso |
| --- | --- |
| `materias_e_learning.parquet` | `SIS_SOURCE_ID` enlaza con `sis_source_id` de Canvas. `ESELEARNING == S` determina el alcance E-Learning. `MATERIA`, `CODACAD` y `TIPOMATERIA` aportan materia, unidad y tipo. |
| `canvas_grado.parquet` | Cursos de GRADO; ID, nombre, paralelo (`course_code`), período, cuota MB y uso MB. |
| `canvas_postgrado.parquet` | Mismo esquema, nivel POSGRADO. Se conserva separado de grado: un mismo `course_id` puede existir en ambas instancias. |
| `cuota_asignada.parquet` | `storage_quota_gb`, enlazado por `id = course_id`, rellena cuotas ausentes/no positivas **solo de grado**. |

La asignación de la tabla auxiliar a grado es una **suposición explícita**: el notebook no documenta su instancia; sus IDs observados van de 42454 a 45768. No se usa sobre posgrado para evitar colisiones entre instancias. Si su procedencia real es otra, ajustar esta regla en `data.py` antes de utilizarla para ese nivel. Una cuota positiva de `canvas_*.quota_mb` siempre tiene prioridad; el CSV incluye `fuente_cuota` para auditar cada valor.

Se conserva cada curso Canvas aunque no tenga coincidencia en el catálogo; aparece en “Todos los cursos Canvas”, con su nombre original y los metadatos faltantes indicados. No se deduce E-Learning de que exista consumo. El paralelo se extrae de `ParaleloN_...`. Sin evidencia del tipo de materia no se presume “Teórica”.

Conversión decimal: `quota_mb / 1000`, `used_mb / 1000`; la cuota auxiliar ya está en GB. Se recalcula `% usado = used / assigned * 100` sobre los valores sin redondear, en lugar de reutilizar `used_percent`. Los límites se evalúan antes del redondeo visual. El porcentaje global es ponderado por capacidad y solo incluye cursos con cuota positiva y uso válido. Las tarjetas suman los valores conocidos de todos los cursos filtrados, por lo que, si hay datos incompletos, su cociente puede diferir del indicador global.

Los valores nulos, negativos o no finitos no equivalen a cero. Los cursos sin porcentaje quedan en el detalle como “Sin cuota / uso” y se excluyen de los tres paneles. Los duplicados exactos se consolidan; registros contradictorios con la misma clave detienen la carga para evitar totales inflados.

La caché dura cinco minutos. “Actualizar datos” vuelve a leer los cuatro archivos; se muestra el intervalo de sus fechas de modificación en Guayaquil, no una fecha de extracción inventada. El productor debe publicar archivos compatibles entre sí.

## Ejecución en el servidor

Desde la raíz del repositorio, con `.env` configurado y el stack disponible:

```bash
docker compose config --quiet
docker compose build dashboard-pbi-canvas
docker compose up -d dashboard-pbi-canvas traefik
docker compose logs --tail=100 dashboard-pbi-canvas
```

Abrir `http://SERVER_IP/pbi-canvas`. El router de archivos de Traefik se actualiza automáticamente. No se publica un puerto nuevo ni se cambia la persistencia del stack.

La autenticación usa `dashboards/common/auth.py` y los usuarios existentes en `config.yaml`, con una cookie propia `pbi_canvas_auth`. Ambos roles pueden consultar las mismas vistas. La configuración inicial conserva cuentas de demostración heredadas: gestionar las cuentas autorizadas antes de compartir el acceso. Microsoft Entra sigue siendo opcional mediante `.streamlit/secrets.toml` y la lista permitida del proyecto, como explica `STREAMLIT_GUIDE.md`.

## Verificación

```bash
python -m unittest discover -s dashboards/pbi-canvas/tests -v
```

Prueba las uniones, colisiones de ID entre niveles, cuotas auxiliares, ausentes, porcentaje ponderado, límites de categoría, duplicados y escape de HTML. La comprobación final en servidor debe verificar el login, ambas pestañas, filtros y cifras frente a los Parquet vigentes. Las capturas son una referencia visual; el notebook contiene datos de otras extracciones y no permite garantizar sus mismos totales.

APIs de pestañas y caché verificadas en la documentación oficial de Streamlit: [st.tabs](https://docs.streamlit.io/develop/api-reference/layout/st.tabs), [st.cache_data](https://docs.streamlit.io/develop/api-reference/caching-and-state/st.cache_data).
