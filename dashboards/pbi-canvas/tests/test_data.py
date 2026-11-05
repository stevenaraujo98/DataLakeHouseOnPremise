import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from data import build_courses, category, summarize, CATEGORIES
from views import overview_html, distribution_html


def course(course_id=1):
    return dict(course_id=course_id, sis_source_id="MAT_1", course_name="Original",
                PARALELO="P12", term_name="2026", quota_mb=999999,
                used_gb=5)


def tables():
    return {
        "materias_e_learning": [dict(SIS_SOURCE_ID="MAT_1", ESELEARNING="S", MATERIA="Materia", CODACAD="FIEC", TIPOMATERIA="teorica")],
        "canvas": [course()], "cuota_asignada": [dict(id=1, storage_quota_gb=10)],
    }


class CanvasDataTests(unittest.TestCase):
    def test_thresholds_are_exclusive(self):
        self.assertEqual([category(x) for x in (79.99, 80, 95, 95.01, 122)], [CATEGORIES[0], CATEGORIES[1], CATEGORIES[1], CATEGORIES[2], CATEGORIES[2]])
        self.assertEqual(category(None), "Sin cuota / uso")

    def test_join_and_decimal_units(self):
        row = build_courses(tables())[0]
        self.assertEqual((row["materia"], row["paralelo"], row["assigned"], row["used"], row["percent"]), ("Materia", "P12", 10, 5, 50))

    def test_inner_join_uses_prefiltered_catalog_without_flag(self):
        t = tables()
        del t["materias_e_learning"][0]["ESELEARNING"]
        unmatched = course(2)
        unmatched["sis_source_id"] = "OTHER"
        null_key = course(3)
        null_key["sis_source_id"] = None
        null_meta = dict(t["materias_e_learning"][0], SIS_SOURCE_ID=None)
        t["materias_e_learning"].append(null_meta)
        t["canvas"] += [unmatched, null_key]
        self.assertEqual([r["id"] for r in build_courses(t)], [1])

    def test_quota_table_is_authoritative_for_both_levels(self):
        t = tables()
        t["materias_e_learning"][0]["CODACAD"] = "POSGRADO"
        t["cuota_asignada"][0]["storage_quota_gb"] = 20
        row = build_courses(t)[0]
        self.assertEqual((row["nivel"], row["assigned"], row["used"], row["percent"]), ("POSGRADO", 20, 5, 25))
        self.assertEqual(row["fuente_cuota"], "cuota_asignada.storage_quota_gb")
        t["cuota_asignada"] = []
        self.assertIsNone(build_courses(t)[0]["assigned"])
        self.assertIsNone(build_courses(t)[0]["percent"])

    def test_invalid_usage_and_quota_are_not_zero(self):
        t = tables()
        for value in (None, float("nan"), float("inf"), -1):
            t["canvas"][0]["used_gb"] = value
            row = build_courses(t)[0]
            self.assertIsNone(row["percent"])
            self.assertIsNone(summarize([row])["used"])
        t["canvas"][0]["used_gb"] = 0
        t["cuota_asignada"][0]["storage_quota_gb"] = 0
        self.assertIsNone(build_courses(t)[0]["percent"])
        t["cuota_asignada"][0]["storage_quota_gb"] = 10
        self.assertEqual(build_courses(t)[0]["percent"], 0)

    def test_weighted_global_usage_excludes_incomplete_rows(self):
        t = tables()
        second = course(2)
        second["used_gb"] = 20
        t["cuota_asignada"].append(dict(id=2, storage_quota_gb=20))
        third = course(3)
        third["used_gb"] = 999999
        t["canvas"] += [second, third]
        result = summarize(build_courses(t))
        self.assertAlmostEqual(result["percent"], 25 / 30 * 100)
        self.assertEqual(result["courses"], 3)

    def test_duplicates_cannot_multiply_totals(self):
        t = tables()
        t["canvas"].append(dict(t["canvas"][0]))
        self.assertEqual(len(build_courses(t)), 1)
        t["canvas"][1]["used_gb"] = 9000
        with self.assertRaises(ValueError):
            build_courses(t)

    def test_html_escapes_gold_text_and_keeps_overcapacity(self):
        t = tables()
        t["materias_e_learning"][0]["MATERIA"] = '<script>alert("x")</script>'
        t["canvas"][0]["used_gb"] = 12.21
        rows = build_courses(t)
        html = overview_html(rows, summarize(rows)) + distribution_html(rows)
        self.assertNotIn('<script>', html)
        self.assertIn('&lt;script&gt;', html)
        self.assertIn('122,10 %', html)
        self.assertIn('No hay cursos en esta categoría.', html)


if __name__ == "__main__":
    unittest.main()
