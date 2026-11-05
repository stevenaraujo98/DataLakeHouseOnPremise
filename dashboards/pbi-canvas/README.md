# Canvas · Almacenamiento

Dos pestañas basadas en Power BI: **Capacidad y uso** (tarjetas, indicador global, detalle y CSV) y **Distribución por consumo** (tres paneles: `<80`, `80–95` y `>95`). Los filtros por nivel, unidad, período/cohorte, tipo y búsqueda afectan ambas vistas.

## Datos y relaciones

El contrato sigue el notebook corregido `notebooks/4_dashboard_canvas.ipynb`. Se leen estos tres archivos bajo `s3://processed-data/gold/PowerBI/Canvas/`:

| Archivo | Relación y uso |
| --- | --- |
| `canvas.parquet` | Cursos: `course_id`, `sis_source_id`, `course_name`, `term_name`, `used_gb`, `PARALELO`. |
| `materias_e_learning.parquet` | **Inner join**: `canvas.sis_source_id = materias_e_learning.SIS_SOURCE_ID`. Gold ya está filtrado a E-Learning; no se vuelve a filtrar por `ESELEARNING`, ni es obligatorio que esa columna exista. Aporta `MATERIA`, `CODACAD` y `TIPOMATERIA`. |
| `cuota_asignada.parquet` | `canvas.course_id = cuota_asignada.id`. `storage_quota_gb` es la capacidad asignada para todos los cursos, incluidos los de posgrado. |

No se leen `canvas_grado.parquet` ni `canvas_postgrado.parquet`. Se retiró la suposición de que las cuotas solo correspondían a grado. Tampoco se usa `quota_mb` como respaldo: si falta la cuota relacionada, el curso permanece en el detalle como “Sin cuota / uso”.

`used_gb` y `storage_quota_gb` **ya están en GB**: no se dividen entre 1.000. El paralelo procede de `PARALELO`. Se recalcula el porcentaje con `used_gb / storage_quota_gb * 100`, en lugar del `used_percent` de Canvas, que puede estar basado en otra cuota.

Solo aparecen cursos con coincidencia en el catálogo de materias. Las claves nulas no coinciden. Los duplicados idénticos se consolidan; las claves con registros contradictorios detienen la carga para evitar multiplicar las cifras. El notebook muestra 1.039 materias, 1.036 claves no nulas distintas y 3.927 cursos Canvas: el total visible depende de su intersección.

La unidad procede de `CODACAD`. Para el filtro de nivel, `CODACAD = POSGRADO` se etiqueta POSGRADO y las demás unidades informadas se etiquetan GRADO; una unidad ausente queda sin nivel.

Los valores nulos, negativos o no finitos no se convierten en cero. El uso cero es válido; una cuota cero no permite calcular un porcentaje. Los límites se evalúan antes del redondeo: 80 % y 95 % pertenecen a la categoría intermedia. El indicador global es ponderado por capacidad y solo incluye cursos con cuota positiva y uso válido. Las tarjetas suman valores conocidos, por lo que su cociente puede diferir del indicador si hay datos incompletos.

La caché dura cinco minutos; “Actualizar datos” relee los tres archivos. Se muestra el intervalo de fechas de modificación en Guayaquil. Las barras conservan porcentajes superiores a 100 %; cada panel usa una escala propia de al menos 100 %.

## Ejecución

Desde la raíz, con el stack y `.env` configurados:

```bash
docker compose config --quiet
docker compose build dashboard-pbi-canvas
docker compose up -d dashboard-pbi-canvas traefik
```

Para aplicar cambios Python en un despliegue existente, con el código montado:

```bash
docker compose restart dashboard-pbi-canvas
```

Abrir `http://SERVER_IP/pbi-canvas`. No cambia la persistencia. La autenticación conserva los usuarios de `config.yaml` y la cookie propia `pbi_canvas_auth`, mediante `dashboards/common/auth.py`. Microsoft Entra sigue siendo opcional según `STREAMLIT_GUIDE.md`.

## Verificación

```bash
python -m unittest discover -s dashboards/pbi-canvas/tests -v
```

Las pruebas cubren inner join, claves nulas, catálogo sin bandera, cuotas de ambos niveles, GB, ausentes, categorías, indicador ponderado, duplicados y escape HTML. La comprobación con MinIO real, login y ambas pestañas debe completarse en el servidor.
