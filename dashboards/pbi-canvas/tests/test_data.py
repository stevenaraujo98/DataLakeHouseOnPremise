import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from data import build_courses, category, summarize, CATEGORIES
from views import overview_html, distribution_html


def course(course_id=1):
    return dict(course_id=course_id, sis_source_id="MAT_1", course_name="Original",
                course_code="Paralelo12_MAT", term_name="2026", quota_mb=10000,
                used_mb=5000)


def tables():
    return {
        "materias_e_learning": [dict(SIS_SOURCE_ID="MAT_1", ESELEARNING="S", MATERIA="Materia", CODACAD="FIEC", TIPOMATERIA="teorica")],
        "canvas_grado": [course()], "canvas_postgrado": [], "cuota_asignada": [],
    }


class CanvasDataTests(unittest.TestCase):
    def test_thresholds_are_exclusive(self):
        self.assertEqual([category(x) for x in (79.99, 80, 95, 95.01, 122)], [CATEGORIES[0], CATEGORIES[1], CATEGORIES[1], CATEGORIES[2], CATEGORIES[2]])
        self.assertEqual(category(None), "Sin cuota / uso")

    def test_join_and_decimal_units(self):
        row = build_courses(tables())[0]
        self.assertEqual((row["materia"], row["paralelo"], row["assigned"], row["used"], row["percent"]), ("Materia", "P12", 10, 5, 50))
        self.assertTrue(row["elearning"])

    def test_auxiliary_quota_is_fallback_for_grado_only(self):
        t = tables()
        t["canvas_grado"][0]["quota_mb"] = None
        t["canvas_postgrado"] = [dict(t["canvas_grado"][0])]
        t["cuota_asignada"] = [dict(id=1, storage_quota_gb=20)]
        rows = build_courses(t)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["percent"], 25)
        self.assertIsNone(rows[1]["percent"])
        t["canvas_grado"][0]["quota_mb"] = 10000
        self.assertEqual(build_courses(t)[0]["assigned"], 10)

    def test_invalid_usage_and_quota_are_not_zero(self):
        t = tables()
        for value in (None, float("nan"), float("inf"), -1):
            t["canvas_grado"][0]["used_mb"] = value
            row = build_courses(t)[0]
            self.assertIsNone(row["percent"])
            self.assertIsNone(summarize([row])["used"])
        t["canvas_grado"][0].update(used_mb=0, quota_mb=0)
        self.assertIsNone(build_courses(t)[0]["percent"])
        t["canvas_grado"][0]["quota_mb"] = 10000
        self.assertEqual(build_courses(t)[0]["percent"], 0)

    def test_weighted_global_usage_excludes_incomplete_rows(self):
        t = tables()
        second = course(2)
        second.update(quota_mb=20000, used_mb=20000)
        third = course(3)
        third.update(quota_mb=None, used_mb=999999)
        t["canvas_grado"] += [second, third]
        result = summarize(build_courses(t))
        self.assertAlmostEqual(result["percent"], 25 / 30 * 100)
        self.assertEqual(result["courses"], 3)

    def test_duplicates_cannot_multiply_totals(self):
        t = tables()
        t["canvas_grado"].append(dict(t["canvas_grado"][0]))
        self.assertEqual(len(build_courses(t)), 1)
        t["canvas_grado"][1]["used_mb"] = 9000
        with self.assertRaises(ValueError):
            build_courses(t)

    def test_html_escapes_gold_text_and_keeps_overcapacity(self):
        t = tables()
        t["materias_e_learning"][0]["MATERIA"] = '<script>alert("x")</script>'
        t["canvas_grado"][0]["used_mb"] = 12210
        rows = build_courses(t)
        html = overview_html(rows, summarize(rows)) + distribution_html(rows)
        self.assertNotIn('<script>', html)
        self.assertIn('&lt;script&gt;', html)
        self.assertIn('122,10 %', html)
        self.assertIn('No hay cursos en esta categoría.', html)


if __name__ == "__main__":
    unittest.main()
