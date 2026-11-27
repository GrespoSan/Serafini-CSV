"""GEX charts: source fidelity, Edge-style readability and no hidden strike panel.

These tests use synthetic data only and do not call network APIs.
"""
from __future__ import annotations

import copy
import math
from pathlib import Path
import unittest

import plotly.graph_objects as go

from csv_gex_panel import (
    GEX_STRIKE_WINDOWS, _curve_chart, _strikes_chart, _strike_window,
)


def example_report():
    spot = 7200.0
    rows = []
    for strike in range(6800, 7601, 10):
        c = (0.04 + abs(math.sin(strike / 75)) * .15) * 1e9
        p = -(0.03 + abs(math.cos(strike / 115)) * .11) * 1e9
        rows.append({
            "strike": float(strike), "call_gex": c,
            "put_gex": p, "net_gex": c + p,
        })
    curve = [
        {"spot": 6480 + j * 7.2,
         "net_gex": (math.sin(j / 35) * 8 - 2) * 1e9}
        for j in range(201)
    ]
    return {
        "call_wall": 7300.0, "put_wall": 7100.0,
        "flip": 7240.25, "rows": rows, "curve": curve,
    }, spot


class GEXChartLayoutTests(unittest.TestCase):
    def test_visible_primary_chart_with_default_2_percent_and_4_choices(self):
        panel = (Path(__file__).resolve().parents[1] /
                 "csv_gex_panel.py").read_text(encoding="utf-8")
        self.assertEqual(GEX_STRIKE_WINDOWS, ("±2%", "±5%", "±10%", "Tutti"))
        self.assertNotIn('with st.expander("GEX per strike', panel)
        self.assertIn('st.subheader("GEX by Strike · composizione Call / Put — 0DTE (Daily)")', panel)
        self.assertIn('st.segmented_control(', panel)
        self.assertIn('default="±2%"', panel)
        self.assertIn('spot=info["spot"]', panel)
        self.assertIn('st.subheader("Curva teorica GEX · scenario prezzo — 0DTE (Daily)")', panel)
        self.assertLess(
            panel.index('st.subheader("GEX by Strike · composizione Call / Put — 0DTE (Daily)")'),
            panel.index('st.subheader("Curva teorica GEX · scenario prezzo — 0DTE (Daily)")'),
        )
        self.assertLess(
            panel.index('st.plotly_chart(\n            strike_fig'),
            panel.index('_live_es_curve(\n            report,info["spot"]'),
        )
        self.assertNotIn('st.radio("Scadenza GEX"', panel)
        self.assertIn('st.html(_gex_summary_card_html(', panel)
        self.assertIn('"Weekly", reports.get("Weekly")', panel)
        self.assertIn('"0DTE", reports.get("0DTE")', panel)
        self.assertIn('key="csv_gex_strikes_0DTE"', panel)
        self.assertIn('es_spx_basis=es_spx_basis,selected="0DTE"', panel)

    def test_2_5_10_and_all_only_filter_display_not_report(self):
        report, spot = example_report()
        original = copy.deepcopy(report)
        lengths = []
        for name in GEX_STRIKE_WINDOWS:
            with self.subTest(name=name):
                fig = _strikes_chart(
                    report, symbol="SPX", spot=spot,
                    es_spx_basis=17.0, window=name,
                )
                lengths.append(fig.layout.meta["strike_visible"])
                self.assertEqual(fig.layout.meta["strike_total"], 81)
                self.assertEqual(fig.layout.meta["window"], name)
                self.assertIsInstance(fig.to_plotly_json(), dict)
        self.assertTrue(lengths[0] < lengths[1] < lengths[2] <= lengths[3])
        self.assertEqual(lengths[-1], 81)
        self.assertEqual(original, report)

    def test_puts_left_calls_right_with_levels_right_es(self):
        report, spot = example_report()
        fig = _strikes_chart(report, symbol="SPX", spot=spot,
                             es_spx_basis=17.0, window="±2%")
        bars = [trace for trace in fig.data if isinstance(trace, go.Bar)]
        self.assertEqual([trace.name for trace in bars], ["PUTS −", "CALLS +"])
        self.assertEqual(bars[0].marker.color, "#9134d7")
        self.assertEqual(bars[1].marker.color, "#80d80c")
        self.assertTrue(all(v < 0 for v in bars[0].x))
        self.assertTrue(all(v > 0 for v in bars[1].x))
        self.assertTrue(all(spot*.98+17-1 < p < spot*1.02+17+1
                            for p in bars[0].y))
        self.assertEqual(len(fig.layout.annotations), 4)
        labels = [a.text for a in fig.layout.annotations]
        for name, value in (
            ("CALL WALL / ES", "7,317.00"),
            ("PUT WALL / ES", "7,117.00"),
            ("GAMMA FLIP / ES", "7,257.25"),
            ("SPOT CSV · ORA FOTOGRAFIA / ES", "7,217.00"),
        ):
            self.assertTrue(any(name in text and value in text
                                for text in labels), (name, value, labels))
        self.assertTrue(all(a.xref == "paper" and a.x > 1
                            for a in fig.layout.annotations))
        self.assertEqual(fig.layout.margin.r, 250)
        self.assertTrue(fig.layout.showlegend)
        self.assertEqual(fig.layout.height, 760)
        xlo, xhi = fig.layout.xaxis.range
        self.assertAlmostEqual(xlo, -xhi)

    def test_outside_window_levels_not_misplotted(self):
        report, spot = example_report()
        report["call_wall"] = 7550
        fig = _strikes_chart(report, symbol="SPX", spot=spot,
                             es_spx_basis=17.0, window="±2%")
        self.assertIn("Call Wall", fig.layout.meta["offscreen_levels"])
        self.assertFalse(any("CALL WALL" in x.text
                             for x in fig.layout.annotations))
        all_figure = _strikes_chart(
            report, symbol="SPX", spot=spot, es_spx_basis=17.0,
            window="Tutti",
        )
        self.assertTrue(any("CALL WALL" in x.text
                            for x in all_figure.layout.annotations))
        self.assertEqual(report["call_wall"], 7550)

    def test_curve_has_legend_and_no_colliding_top_bottom_annotations(self):
        report, spot = example_report()
        quote = {"price": 7250.25, "symbol": "ESZ26.CME"}
        fig = _curve_chart(
            report, spot, symbol="SPX", es_spx_basis=17,
            es_quote=quote,
        )
        self.assertTrue(fig.layout.showlegend)
        self.assertEqual(fig.layout.legend.orientation, "h")
        names = [trace.name for trace in fig.data]
        for key in ("Curva NET GEX", "Call Wall · ES", "Put Wall · ES",
                    "Gamma Flip · ES", "Spot CSV · ES equivalente (ora fotografia)",
                    "ES Yahoo · 7,250.25 (ESZ26.CME)"):
            self.assertIn(key, names)
        self.assertEqual(len(fig.layout.annotations or ()), 0)
        self.assertEqual(len(report["curve"]), 201)
        self.assertEqual(list(fig.data[0].x)[0], 6497.0)
        self.assertEqual(list(fig.data[0].x)[-1], 7937.0)

    def test_spot_and_yahoo_are_colored_dots_on_existing_curve(self):
        report, spot = example_report()
        frozen = copy.deepcopy(report)
        actual = 7250.25
        fig = _curve_chart(
            report, spot, symbol="SPX", es_spx_basis=17.0,
            es_quote={"price": actual, "symbol": "ESZ26.CME"},
        )
        spot_trace = next(t for t in fig.data
                          if t.name == "Spot CSV · ES equivalente (ora fotografia)")
        yahoo_trace = next(t for t in fig.data
                           if t.name == "ES Yahoo · 7,250.25 (ESZ26.CME)")
        self.assertEqual(spot_trace.mode, "markers")
        self.assertEqual(yahoo_trace.mode, "markers")
        self.assertEqual(spot_trace.marker.color, "#e5e7eb")
        self.assertEqual(yahoo_trace.marker.color, "#fb923c")
        self.assertEqual(spot_trace.marker.size, 10)
        self.assertEqual(yahoo_trace.marker.size, 12)
        self.assertAlmostEqual(spot_trace.x[0], 7217.0)
        self.assertAlmostEqual(yahoo_trace.x[0], actual)
        self.assertEqual(len(spot_trace.x), 1)
        self.assertEqual(len(yahoo_trace.x), 1)
        curve = fig.data[0]
        # L'ordinata è interpolata fra due punti realmente calcolati;
        # né il prezzo ES Yahoo né il NET GEX sono ricalcolati.
        for trace in (spot_trace, yahoo_trace):
            idx = next(i for i in range(1, len(curve.x))
                       if curve.x[i-1] <= trace.x[0] <= curve.x[i])
            weight = ((trace.x[0] - curve.x[idx-1]) /
                      (curve.x[idx] - curve.x[idx-1]))
            expected_y = (curve.y[idx-1] +
                          weight * (curve.y[idx] - curve.y[idx-1]))
            self.assertAlmostEqual(trace.y[0], expected_y)
        self.assertEqual(frozen, report)
        self.assertEqual(len(curve.x), 201)
        self.assertEqual([t.mode for t in fig.data
                          if t.name.startswith(("Call Wall", "Put Wall",
                                                "Gamma Flip"))],
                         ["lines", "lines", "lines"])

    def test_spot_marker_without_yahoo_quote_and_no_fabricated_quote(self):
        report, spot = example_report()
        fig = _curve_chart(report, spot, symbol="SPX",
                           es_spx_basis=17.0, es_quote=None)
        self.assertEqual(
            next(t for t in fig.data
                 if t.name == "Spot CSV · ES equivalente (ora fotografia)").mode,
            "markers",
        )
        self.assertFalse(any(t.name.startswith("ES Yahoo")
                             for t in fig.data))

    def test_curve_extrema_show_price_not_peak_word_and_no_metric_cards(self):
        from csv_gex_curve import curve_extrema
        report, spot = example_report()
        curve = _curve_chart(report, spot, symbol="SPX", es_spx_basis=17.0)
        expected = curve_extrema(report, symbol="SPX", es_spx_basis=17.0)
        for key, label in (("maximum", "Picco MAX"), ("minimum", "Picco MIN")):
            trace = next(t for t in curve.data if t.name == label)
            self.assertEqual(trace.mode, "markers+text")
            self.assertEqual(list(trace.text),
                             [f"{expected[key]['price']:,.2f}"])
            self.assertNotIn("Picco ", trace.text[0])
        panel = (Path(__file__).resolve().parents[1] /
                 "csv_gex_panel.py").read_text(encoding="utf-8")
        self.assertNotIn("Picco massimo curva", panel)
        self.assertNotIn("Picco minimo curva", panel)
        self.assertLess(
            panel.index('st.subheader("GEX by Strike'),
            panel.index('st.subheader("Curva teorica GEX'),
        )

    def test_historical_quote_outside_range_does_not_stretch_curve(self):
        report, spot = example_report()
        fig = _curve_chart(
            report, spot, symbol="SPX", es_spx_basis=17.0,
            es_quote={"price": 10000.0, "symbol": "ESZ26.CME"},
        )
        self.assertFalse(any(
            x.name.startswith("ES Yahoo") for x in fig.data
        ))

    def test_other_markets_keep_original_strike_scale(self):
        report, spot = example_report()
        fig = _strikes_chart(report, symbol="NDX", spot=spot,
                             window="±2%")
        values = [a.text for a in fig.layout.annotations]
        self.assertTrue(any("CALL WALL / NDX" in a
                            and "7,300.00" in a for a in values))
        self.assertNotIn("equivalente ES", fig.layout.yaxis.title.text)

    def test_bad_window_or_missing_es_basis_fails_explicitly(self):
        report, spot = example_report()
        with self.assertRaises(ValueError):
            _strike_window(report["rows"], spot=spot, symbol="SPX",
                           es_spx_basis=17, window="±3%")
        with self.assertRaisesRegex(ValueError, "non convertibile"):
            _strikes_chart(report, symbol="SPX", spot=spot, window="±2%")


if __name__ == "__main__":
    unittest.main()
