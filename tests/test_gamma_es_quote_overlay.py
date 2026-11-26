"""Regressione quote ES indicativa su istogrammi SPX 0DTE e Weekly."""
import copy
from pathlib import Path
import unittest

import plotly.graph_objects as go

from gamma_es_quote_overlay import add_es_quote_to_net_gamma


ROOT = Path(__file__).resolve().parents[1]
QUOTE = {
    "price": 7119.25,
    "source": "YAHOO_FINANCE_CHART",
    "symbol": "ESZ26.CME",
    "observed_rome": "26/11/2026 09:10:00",
    "age_minutes": 5.0,
    "contract_kind": "EXPLICIT",
}


def bars():
    fig = go.Figure(go.Bar(x=[-2.3, 2.4], y=[7100, 7150], orientation="h"))
    fig.update_layout(xaxis=dict(range=[-3, 3]))
    return fig


class QuoteOverlayTests(unittest.TestCase):
    def test_same_genuine_price_on_odte_and_weekly_without_gamma_changes(self):
        for title in ("0DTE", "Weekly"):
            with self.subTest(title=title):
                fig = bars()
                before = list(fig.data[0].x)
                result = add_es_quote_to_net_gamma(
                    fig, [7100, 7150], QUOTE, has_es_axis=True,
                )
                self.assertTrue(result["shown"])
                self.assertFalse(result["outside_strikes"])
                self.assertEqual(result["price"], QUOTE["price"])
                self.assertEqual(before, list(fig.data[0].x))
                self.assertEqual(list(fig.layout.xaxis.range), [-3, 3])
                self.assertEqual(len(fig.layout.shapes), 1)
                shape = fig.layout.shapes[0]
                self.assertEqual(shape.y0, 7119.25)
                self.assertEqual(shape.y1, 7119.25)
                self.assertEqual(shape.line.color, "#fb923c")
                self.assertEqual(len(fig.layout.annotations), 1)
                self.assertIn("ES Yahoo 7,119.25",
                              fig.layout.annotations[0].text)

    def test_out_of_range_price_expands_only_price_axis(self):
        fig = bars()
        result = add_es_quote_to_net_gamma(
            fig, [7100, 7150], dict(QUOTE, price=6900),
            has_es_axis=True,
        )
        self.assertTrue(result["shown"])
        self.assertTrue(result["outside_strikes"])
        self.assertLess(fig.layout.yaxis.range[0], 6900)
        self.assertGreater(fig.layout.yaxis.range[1], 7150)
        self.assertEqual(list(fig.layout.xaxis.range), [-3, 3])

    def test_no_quote_no_offset_or_stale_data_adds_nothing(self):
        cases = [
            (QUOTE, False),
            (None, True),
            (dict(QUOTE, price=None), True),
            (dict(QUOTE, age_minutes=95), True),
            (dict(QUOTE, observed_rome=None), True),
            (dict(QUOTE, source="UNVERIFIED"), True),
            (dict(QUOTE, price=float("nan")), True),
        ]
        for quote, is_es in cases:
            with self.subTest(quote=quote, es=is_es):
                fig = bars()
                before = copy.deepcopy(fig.to_plotly_json())
                result = add_es_quote_to_net_gamma(
                    fig, [7100, 7150], quote, has_es_axis=is_es,
                )
                self.assertFalse(result["shown"])
                self.assertEqual(fig.to_plotly_json(), before)

    def test_control_off_by_default_and_quote_shared_with_gex(self):
        text = (ROOT / "gamma_section.py").read_text(encoding="utf-8")
        gex = (ROOT / "csv_gex_panel.py").read_text(encoding="utf-8")
        self.assertIn("from csv_gex_quote_cache import _cached_es_quote", text)
        self.assertIn("from csv_gex_quote_cache import _cached_es_quote", gex)
        self.assertIn('value=False, key="gamma_percent_lines_v1"', text)
        self.assertIn("if show_percent_lines:\n                    for pct", text)
        self.assertIn("quote_overlay = add_es_quote_to_net_gamma(", text)
        self.assertIn('for (title, expiry), profile_col in zip(', text)
        self.assertIn('font=dict(color="#fb923c", size=12)', (
            ROOT / "gamma_es_quote_overlay.py").read_text(encoding="utf-8"))
        self.assertNotIn("show_percent_lines = st.checkbox(",
                         (ROOT / "pine_export.py").read_text(encoding="utf-8"))

    def test_peak_price_text_has_large_font(self):
        panel = (ROOT / "csv_gex_panel.py").read_text(encoding="utf-8")
        self.assertIn('textfont=dict(size=16, color=color', panel)
        self.assertIn('text=[f"{item[\'price\']:,.2f}"]', panel)


if __name__ == "__main__":
    unittest.main()
