"""Smoke test import reali: GEX service e pannello non possono bloccare l'upload."""
import ast
import importlib
import inspect
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


class GexImportIsolationTests(unittest.TestCase):
    def test_services_import_and_backward_compatible_panel_exports(self):
        service = importlib.import_module("csv_gex_services")
        panel = importlib.import_module("csv_gex_panel")
        for name in ("_cached_gex", "_cached_occ", "OI_LABELS",
                     "DEFAULT_OI_LABEL"):
            with self.subTest(name=name):
                self.assertTrue(hasattr(service, name))
                self.assertIs(getattr(panel, name), getattr(service, name))
        self.assertEqual(
            service.OI_LABELS[service.DEFAULT_OI_LABEL], "auto",
        )
        self.assertTrue(callable(service._cached_gex))
        self.assertTrue(callable(service._cached_occ))

    def test_app_does_not_depend_on_ui_import_during_csv_processing(self):
        app = (ROOT / "app.py").read_text(encoding="utf-8")
        tree = ast.parse(app)
        from_services = [
            node for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
            and node.module == "csv_gex_services"
        ]
        self.assertEqual(len(from_services), 1)
        self.assertNotIn("from csv_gex_panel import (_cached_gex", app)
        self.assertIn("st.session_state['csv_gex_last_error']", app)
        self.assertIn('if market == "SP500":', app)

        # L'import del service GEX deve essere dentro un blocco try protetto:
        # senza GEX il ramo SP500 deve proseguire fino al suo render originale.
        lines = app.splitlines()
        import_line = next(
            i for i, line in enumerate(lines)
            if line.lstrip().startswith("from csv_gex_services import")
        )
        self.assertEqual(
            len(lines[import_line]) - len(lines[import_line].lstrip()), 16
        )
        preceding = "\n".join(lines[:import_line])
        self.assertIn(
            "            try:\n"
            "                # I servizi dati GEX", preceding,
        )

    def test_gex_import_failure_is_separate_from_net_gamma_render(self):
        app = (ROOT / "app.py").read_text(encoding="utf-8")
        self.assertLess(
            app.index("            except Exception as exc:\n"
                      "                # Fallback controllato"),
            app.index('            if market == "SP500":'),
        )
        self.assertIn(
            "st.session_state['csv_gex_last_report'] = None", app,
        )


if __name__ == "__main__":
    unittest.main()
