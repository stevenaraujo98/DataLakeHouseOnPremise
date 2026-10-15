# Dashboard de analítica de Chatbot TH

La aplicación consume `s3://processed-data/gold/th/chatbot/metrics.json`
generado por `notebooks/2_analysis.ipynb`, con `version_esquema: 2`.
El detalle se obtiene de `mensajes.parquet` únicamente al entrar como
administrador en la vista **Detalle**. Las demás vistas usan el JSON agregado;
no necesitan descargar todos los mensajes ni los otros Parquet.

| Vista | Contenido |
|---|---|
| Resumen | KPIs, actividad diaria, sentimientos y usuarios más activos. |
| Conversaciones | Mensajes, palabras y frases de apertura; términos frecuentes de los usuarios. |
| Herramientas | Llamadas, interacciones, usuarios y sesiones por herramienta; P95 asociado. |
| Rendimiento | Media, mediana, P95, máximo, distribución y rankings de sesiones. |
| Incidencias | `error_model`, `Limitante`, `Language_analysis_lizura`, evolución y calidad de datos. |
| Detalle — admin | Búsqueda literal en mensajes/respuestas, filtros por usuario y tipo, descarga CSV. |

El selector de fechas filtra las **gráficas diarias** de actividad, latencias
e incidencias. Los KPIs, los términos frecuentes y los rankings corresponden
al **histórico completo**: los agregados exportados no permiten recalcular
usuarios únicos ni percentiles de cualquier intervalo. El panel distingue
estos alcances en las etiquetas.

Los tiempos de respuesta se muestran en segundos; la duración de sesión,
en minutos. El tiempo acumulado del modelo suma las latencias; la duración
de reloj también incluye las pausas del usuario. Las incidencias no se
cuentan como herramientas. Una interacción con varias etiquetas de
incidencia se cuenta una vez en el total de afectadas.

## Actualizar en el servidor

1. En JupyterHub, ejecutar las celdas de cálculo y preparación de archivos del
   notebook, y después **Publicar resultados gold en MinIO**. Si esa última
   celda está comentada, descomentarla y ejecutarla: preparar los archivos en
   memoria no los publica.
2. Actualizar `dashboards/chatbot-th/app.py` en el repositorio del servidor.
   Compose monta esa carpeta en `/app`; no se cambiaron dependencias ni se
   necesita reconstruir la imagen para este cambio.
3. Desde la raíz del repositorio del servidor:

   ```bash
   docker compose restart dashboard-chatbot-th
   docker compose logs --tail=80 dashboard-chatbot-th
   ```

4. Abrir `http://SERVER_IP/chatbot-th` e iniciar sesión. El botón
   **Actualizar datos** renueva la caché de métricas y detalle, que normalmente
   dura cinco minutos. Verificar las cinco vistas con un usuario cliente y
   **Detalle** con un administrador.

Si el JSON aún tiene el formato anterior, Resumen conserva los datos
disponibles y el panel explica que falta publicar los nuevos resultados.
Un error de permisos de MinIO se muestra separado de un archivo ausente.

El flow `flows/metricas_dashboard_chat_th.py` todavía calcula el formato
anterior. Para automatizar estos resultados hay que trasladarle la lógica
del notebook; una ejecución de ese flow puede volver a publicar el JSON
anterior sobre la misma clave.

## Pruebas sin servidor

En un entorno con las dependencias del dashboard instaladas:

```bash
python -m unittest discover -s dashboards/chatbot-th/tests -v
```

Las pruebas usan Streamlit AppTest, un login simulado y MinIO en memoria.
No requieren credenciales ni conexiones al servidor. Comprueban navegación,
selectores, filtros de fechas, búsqueda, aislamiento por rol, renovación de
caché, compatibilidad con el formato anterior y resultados vacíos.
