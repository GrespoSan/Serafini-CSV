"""La visualizzazione GEX SPX mostra ES soltanto, mai valori SPX grezzi."""
import math
from pathlib import Path
import unittest

from csv_gex_price_display import gex_display_price, gex_price_label


class GEXOnlyESTests(unittest.TestCase):
    def test_spx_levels_projected_with_exact_basis(self):
        basis = 43.25
        self.assertEqual(gex_price_label("SPX"), "ES")
        self.assertAlmostEqual(gex_display_price(7000, "SPX", basis), 7043.25)
        self.assertAlmostEqual(gex_display_price(6825, "SPX", basis), 6868.25)
        self.assertAlmostEqual(gex_display_price(7092.46, "SPX", basis), 7135.71)
        self.assertAlmostEqual(gex_display_price(6960, "SPX", basis), 7003.25)

    def test_missing_basis_never_displays_spx_as_es(self):
        self.assertIsNone(gex_display_price(7000, "SPX", None))
        self.assertIsNone(gex_display_price(7000, "SPX", float("nan")))
        self.assertIsNone(gex_display_price(None, "SPX", 43))

    def test_es_basis_can_be_negative_without_fabricating_values(self):
        self.assertAlmostEqual(gex_display_price(7000, "SPX", -35), 6965)
        with self.assertRaises(ValueError):
            gex_display_price(-1, "SPX", 43)

    def test_other_tickers_unchanged_and_not_converted_to_es(self):
        for market in ("NDX", "RUT", "DJX", "GLD", "USO", "AAPL"):
            self.assertEqual(gex_price_label(market), market)
            self.assertEqual(gex_display_price(120, market, None), 120)
            self.assertEqual(gex_display_price(120, market, 100), 120)

    def test_spx_panel_reuses_net_gamma_basis_and_reprojects_price_axes(self):
        base = Path(__file__).resolve().parents[1]
        app = (base / "app.py").read_text(encoding="utf-8")
        g = (base / "gamma_section.py").read_text(encoding="utf-8")
        panel = (base / "csv_gex_panel.py").read_text(encoding="utf-8")
        self.assertIn("'es_spx_basis': offset", g)
        self.assertIn("asia_panel.get('es_spx_basis')", app)
        self.assertIn("es_spx_basis=es_spx_basis", panel)
        self.assertIn("gex_display_price(report[field], symbol, es_spx_basis)", panel)
        self.assertIn('gex_display_price(row["spot"], symbol, es_spx_basis)', panel)
        self.assertIn('gex_display_price(r["strike"], symbol, es_spx_basis)', panel)
        self.assertIn("if basis_available:\n        st.plotly_chart(", panel)
        self.assertIn("**Livelli esclusivamente ES/MES**", panel)


if __name__ == "__main__":
    unittest.main()
