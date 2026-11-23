"""Automatic single-CSV GEX -> Pine wiring, no extra buttons or toggles.

These regressions explicitly safeguard the ordering of the Streamlit caller.
The GEX mathematical/regime/quality gates are tested separately.
"""
from pathlib import Path
import unittest
import ast
from datetime import datetime
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]


class AutoGexFlowTests(unittest.TestCase):
    def source(self, path):
        return (ROOT / path).read_text(encoding="utf-8")

    def test_one_upload_calculates_gex_before_every_pine_market_renderer(self):
        app = self.source("app.py")
        compute = app.index("gex_report = _cached_gex(csv_bytes, symbol, iv_mode)")
        assign = app.index("st.session_state['csv_gex_last_report'] = (")
        spx = app.index('if market == "SP500":', compute)
        generic = app.index("photo_day = render_market(upload, symbol, equity)", compute)
        self.assertLess(compute, assign)
        self.assertLess(assign, spx)
        self.assertLess(assign, generic)
        self.assertLess(app.index("ticker_azione_da_csv(upload.getvalue())"), compute)
        self.assertIn("st.session_state['csv_gex_last_error']", app)

    def test_no_second_button_or_export_toggle(self):
        panel = self.source("csv_gex_panel.py")
        controls = self.source("mercati/pine_ui.py")
        self.assertNotIn('st.button("Calcola GEX', panel)
        self.assertNotIn("st.rerun()", panel)
        self.assertIn('st.session_state.get("csv_gex_last_report")', panel)
        self.assertNotIn("st.toggle(", controls)
        self.assertNotIn("pine_gex_enabled_", controls)
        self.assertIn("output = append_csv_gex(", controls)
        self.assertIn('st.caption(f"GEX non incluso nel Pine', controls)

    def test_pine_uses_original_file_identity_and_shared_code(self):
        controls = self.source("mercati/pine_ui.py")
        self.assertIn('source.get("symbol") != source_ticker', controls)
        self.assertIn('st.session_state.get("csv_gex_last_report")', controls)
        self.assertIn("data=code", controls)
        self.assertIn("st.code(code, language=None", controls)
        self.assertIn("return code", controls)
        spx = self.source("gamma_section.py")
        self.assertIn("prepare_pine_with_csv_gex(", spx)
        markets = {
            "mercati/v2_market_engine.py": "source_ticker='NDX'",
            "mercati/v2_index_market_view.py": "source_ticker=ticker",
            "mercati/gld_cboe_view.py": "source_ticker='GLD'",
            "mercati/uso_cboe_view.py": "source_ticker='USO'",
            "mercati/v2_universal_cboe.py": "source_ticker=ticker",
        }
        for name, marker in markets.items():
            with self.subTest(market=name):
                self.assertIn(marker, self.source(name))

    def test_csv_cboe_time_is_source_utc_not_download_time(self):
        # Isola l'helper puro senza importare Streamlit o scaricare snapshot.
        source = self.source("gamma_section.py")
        tree = ast.parse(source)
        method = next(
            item for item in tree.body
            if isinstance(item, ast.FunctionDef)
            and item.name == "_csv_cboe_capture_label"
        )
        namespace = {"datetime": datetime, "ZoneInfo": ZoneInfo}
        exec(compile(ast.Module(body=[method], type_ignores=[]),
                     "<csv_time_test>", "exec"), namespace)
        caption = namespace["_csv_cboe_capture_label"]
        snapshot = {
            "timestamp": "2026-11-23 07:22:00",
            "_import_provenance": {
                "source": "CBOE_CSV_MANUAL_USER_EXPORT",
                "timestamp_utc_converted": True,
            },
        }
        self.assertEqual(
            caption(snapshot), "Fotografia CSV Cboe · ore 08:22 Roma"
        )
        self.assertIsNone(caption({"timestamp": "2026-11-23 07:22:00"}))
        bad = dict(snapshot, timestamp="not-a-time")
        self.assertIn("ora fonte non verificabile", caption(bad))
        self.assertIn(
            "csv_capture_label if csv_capture_label is not None",
            source,
        )
        self.assertIn(
            "capture_info = (\n                csv_capture_label",
            source,
        )

    def test_same_csv_and_mode_are_mandatory_before_insertion(self):
        from csv_gex_pine import validate_result
        report = {"sha256": "1"*64, "symbol": "SPX",
                  "source": "CBOE_CSV_MANUAL_USER_EXPORT",
                  "quality_certified": False,
                  "reports": {"0DTE": {"status": "INSUFFICIENTE"},
                              "Weekly": {"status": "INSUFFICIENTE"}}}
        source = {"sha256": "1"*64, "symbol": "SPX"}
        signature = ("1"*64, "SPX", "auto")
        with self.assertRaisesRegex(ValueError, "qualità diagnostica"):
            validate_result((signature, report), source, "auto")
        with self.assertRaisesRegex(ValueError, "ricalcolare"):
            validate_result((signature, report), {"sha256": "2"*64, "symbol": "SPX"}, "auto")


if __name__ == "__main__":
    unittest.main()
