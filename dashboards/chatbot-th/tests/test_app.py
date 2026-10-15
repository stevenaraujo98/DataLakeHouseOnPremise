"""Pruebas de las vistas con Streamlit AppTest y MinIO simulado, sin credenciales."""

import copy
import io
import json
import os
import sys
import types
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

import polars as pl
import streamlit as st
from botocore.exceptions import ClientError
from streamlit.testing.v1 import AppTest


APP = Path(__file__).resolve().parents[1] / "app.py"
PRIVADO = "MENSAJE_PRIVADO_DE_PRUEBA"


def metricas_ejemplo():
    actividad = [
        {
            "fecha": fecha, "interacciones": interacciones, "respuestas": respuestas,
            "usuarios": usuarios, "sesiones": usuarios,
            "latencia_media_ms": 1500, "latencia_p50_ms": 1500,
            "latencia_p95_ms": 1950, "error_model": error, "Limitante": error,
            "Language_analysis_lizura": 0, "interacciones_con_incidencia": error,
            "tasa_incidencias_pct": 50.0 if error else 0.0,
        }
        for fecha, interacciones, respuestas, usuarios, error in [
            ("2026-10-14", 2, 1, 2, 1), ("2026-10-15", 1, 1, 1, 0),
        ]
    ]
    sesion = {
        "usuario_cedula": "0001", "session_id": "s1", "interacciones": 2,
        "respuestas": 2, "tiempo_modelo_total_s": 3.0,
        "latencia_max_ms": 2000, "duracion_min": 12.0,
        "mensaje_inicio": PRIVADO,
    }
    termino = {"termino": "permiso de maternidad", "frecuencia": 3,
               "mensajes": 2, "usuarios": 2, "sesiones": 2, "n_palabras": 3}
    return {
        "version_esquema": 2, "generado_en": "2026-10-15T17:00:00+00:00",
        "zona_horaria": "America/Guayaquil", "total_mensajes": 3,
        "total_interacciones": 3, "total_respuestas": 2, "total_usuarios": 2,
        "total_sesiones": 2, "total_errores": 1, "total_sin_respuesta": 1,
        "tasa_respuesta_pct": 66.67, "tasa_incidencias_pct": 33.33,
        "usa_tool_counts": {"True": 2, "False": 1},
        "sentiment_counts": {"Neutral": 2, "Positive": 1},
        "tools_counts": {"agente_normativa": 3},
        "mensajes_por_dia": {"2026-10-14": 2, "2026-10-15": 1},
        "actividad_diaria": actividad, "incidencias_por_dia": actividad,
        "top_usuarios": {"0001": 2, "0002": 1},
        "top_usuarios_detalle": [{"usuario_cedula": "0001", "interacciones": 2,
                                  "respuestas": 2, "sesiones": 1}],
        "inicios_sesion": {
            "sesiones_con_inicio_observable": 2,
            "mensajes_frecuentes": [{"mensaje": "hola", "sesiones": 2}],
            "palabras_frecuentes": [dict(termino, termino="hola")],
            "frases_frecuentes": [dict(termino, termino="buenos dias")],
        },
        "mensajes_corpus_tematico": 2,
        "palabras_clave": [dict(termino, termino="maternidad", n_palabras=1)],
        "frases_clave": [termino],
        "herramientas": [{"tool": "agente_normativa", "llamadas": 3,
                           "interacciones": 2, "usuarios": 1, "sesiones": 1,
                           "latencia_media_ms": 1500, "latencia_p95_ms": 1950}],
        "incidencias_counts": {"error_model": 1, "Limitante": 1, "Language_analysis_lizura": 0},
        "latencias": {"respuestas_con_latencia": 2, "media_ms": 1500,
                      "p50_ms": 1500, "p95_ms": 1950, "max_ms": 2000},
        "distribucion_latencias": [{"rango": "1–3 s", "respuestas": 2}],
        "sesion_mas_lenta_por_usuario": [sesion], "top_sesiones_tiempo_modelo": [sesion],
        "top_sesiones_duracion": [sesion],
        "respuestas_mas_lentas": [{"id": 1, "response_latency_ms": 2000}],
        "calidad_datos": {"respuestas_sin_latencia_valida": 0},
    }


class MinioSimulado:
    def __init__(self):
        self.metricas = metricas_ejemplo()
        self.lecturas = []
        self.error = None
        self.detalle = pl.DataFrame({
            "created_at": ["2026-10-14 10:00:00-05:00", "2026-10-15 10:00:00-05:00"],
            "usuario_cedula": ["0001", "0002"], "session_id": ["s1", "s2"],
            "content": [PRIVADO, "hola"], "respuesta_ia": ["permiso aprobado", None],
            "hay_respuesta": [True, False], "tiene_incidencia": [True, False],
            "usa_tool": [True, False], "response_latency_s": [2.0, None],
        })

    def get_object(self, Bucket, Key):
        assert Bucket == "processed-data"
        self.lecturas.append(Key)
        if self.error:
            raise ClientError({"Error": {"Code": self.error}}, "GetObject")
        if Key.endswith("metrics.json"):
            contenido = json.dumps(self.metricas).encode()
        elif Key.endswith("mensajes.parquet"):
            buffer = io.BytesIO()
            self.detalle.write_parquet(buffer)
            contenido = buffer.getvalue()
        else:
            raise AssertionError(f"Lectura inesperada: {Key}")
        return {"Body": io.BytesIO(contenido)}


class DashboardTest(unittest.TestCase):
    def setUp(self):
        st.cache_data.clear()
        st.cache_resource.clear()
        self.minio = MinioSimulado()
        self.rol = "cliente"
        auth = types.ModuleType("common.auth")
        auth.login_gate = lambda: ("demo", self.rol)
        common = types.ModuleType("common")
        common.auth = auth
        # Restaurar solo estos dos módulos; patch.dict(sys.modules) retiraría
        # también dependencias cargadas durante AppTest entre una prueba y otra.
        self.modulos_previos = {nombre: sys.modules.get(nombre) for nombre in ("common", "common.auth")}
        sys.modules.update({"common": common, "common.auth": auth})
        self.patches = [
            patch("boto3.client", return_value=self.minio),
            patch.dict(os.environ, {
                "MINIO_ENDPOINT": "http://minio.test:9000",
                "MINIO_ACCESS_KEY": "test", "MINIO_SECRET_KEY": "test",
            }),
        ]
        for parche in self.patches:
            parche.start()

    def tearDown(self):
        for parche in reversed(self.patches):
            parche.stop()
        for nombre, anterior in self.modulos_previos.items():
            if anterior is None:
                sys.modules.pop(nombre, None)
            else:
                sys.modules[nombre] = anterior
        st.cache_data.clear()
        st.cache_resource.clear()

    def iniciar(self):
        app = AppTest.from_file(str(APP), default_timeout=20).run()
        self.assertEqual(list(app.exception), [])
        return app

    def navegar(self, app, vista):
        app.radio("vista").set_value(vista).run()
        self.assertEqual(list(app.exception), [])

    def test_vistas_cliente_no_leen_detalle_ni_exponen_mensajes_privados(self):
        app = self.iniciar()
        self.assertNotIn("Detalle", app.radio("vista").options)
        for vista in ["Conversaciones", "Herramientas", "Rendimiento", "Incidencias", "Resumen"]:
            self.navegar(app, vista)
            for grafico in app.get("plotly_chart"):
                self.assertNotIn(PRIVADO, grafico.proto.spec)
            for frame in app.dataframe:
                self.assertNotIn(PRIVADO, frame.value.to_string())
        self.assertTrue(all(k.endswith("metrics.json") for k in self.minio.lecturas))

    def test_selectores_de_aperturas_temas_y_rankings(self):
        app = self.iniciar()
        self.navegar(app, "Conversaciones")
        for modo in app.selectbox("modo_apertura").options:
            app.selectbox("modo_apertura").set_value(modo).run()
            self.assertFalse(app.exception)
        app.selectbox("modo_temas").set_value("Frases cortas").run()
        app.selectbox("criterio_temas").set_value("usuarios").run()
        self.assertFalse(app.exception)
        self.navegar(app, "Rendimiento")
        for modo in app.selectbox("ranking_sesiones").options:
            app.selectbox("ranking_sesiones").set_value(modo).run()
            self.assertFalse(app.exception)

    def test_rango_diario_no_cambia_kpis_globales(self):
        app = self.iniciar()
        kpis = [(m.label, m.value) for m in app.metric]
        app.date_input("periodo_diario").set_value((date(2026, 10, 15), date(2026, 10, 15))).run()
        self.assertFalse(app.exception)
        self.assertEqual(kpis, [(m.label, m.value) for m in app.metric])
        grafico = json.loads(app.get("plotly_chart")[0].proto.spec)
        self.assertTrue(all(trace["x"] == ["2026-10-15"] for trace in grafico["data"]))

    def test_admin_detalle_filtros_busqueda_literal_y_cache_por_generacion(self):
        self.rol = "admin"
        app = self.iniciar()
        self.navegar(app, "Detalle")
        self.assertEqual(len(app.dataframe[0].value), 2)
        app.selectbox("detalle_tipo").set_value("Sin respuesta").run()
        self.assertEqual(len(app.dataframe[0].value), 1)
        app.selectbox("detalle_tipo").set_value("Todas").run()
        app.text_input("detalle_buscar").input("[").run()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.dataframe[0].value), 0)
        app.text_input("detalle_buscar").input("permiso").run()
        self.assertEqual(len(app.dataframe[0].value), 1)
        app.text_input("detalle_buscar").input("").run()
        app.multiselect("detalle_usuarios").select("0002").run()
        self.assertEqual(app.dataframe[0].value["usuario_cedula"].tolist(), ["0002"])
        self.assertEqual(sum(k.endswith("mensajes.parquet") for k in self.minio.lecturas), 1)
        self.minio.metricas["generado_en"] = "2026-10-15T18:00:00+00:00"
        app.button("actualizar_datos").click().run()
        self.assertFalse(app.exception)
        self.assertEqual(sum(k.endswith("mensajes.parquet") for k in self.minio.lecturas), 2)

    def test_formato_anterior_explica_publicacion_pendiente(self):
        self.minio.metricas = {k: self.minio.metricas[k] for k in (
            "generado_en", "total_mensajes", "total_usuarios", "total_sesiones", "total_errores",
            "usa_tool_counts", "tools_counts", "sentiment_counts", "top_usuarios", "mensajes_por_dia",
        )}
        app = self.iniciar()
        self.assertTrue(app.warning)
        self.navegar(app, "Rendimiento")
        self.assertTrue(app.info)

    def test_datos_vacios_y_tiempos_ausentes(self):
        vacias = copy.deepcopy(self.minio.metricas)
        for clave, valor in vacias.items():
            if isinstance(valor, list):
                vacias[clave] = []
        vacias.update(inicios_sesion={}, latencias={}, tools_counts={}, top_usuarios={},
                      sentiment_counts={}, mensajes_por_dia={})
        self.minio.metricas = vacias
        app = self.iniciar()
        for vista in ["Conversaciones", "Herramientas", "Rendimiento", "Incidencias"]:
            self.navegar(app, vista)

    def test_archivo_ausente_y_acceso_denegado_se_distinguen(self):
        self.minio.error = "NoSuchKey"
        app = self.iniciar()
        self.assertTrue(app.warning)
        self.assertFalse(app.error)
        self.minio.error = "AccessDenied"
        st.cache_data.clear()
        app.run()
        self.assertFalse(app.exception)
        self.assertTrue(app.error)
        self.assertFalse(app.warning)


if __name__ == "__main__":
    unittest.main()
