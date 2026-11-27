"""GEX: due riquadri Daily/Weekly, stesso report sorgente, nessun chart Weekly.

Non vengono chiamati Yahoo, OCC, Cboe o Streamlit Cloud.
"""
from __future__ import annotations

from pathlib import Path
import unittest

from csv_gex_panel import _gex_summary_card_html

ROOT = Path(__file__).resolve().parents[1]


def valid_report(expiry, **overrides):
    data = {
        "status": "DIAGNOSTICO", "expiry": expiry,
        "contracts": 702, "valid": 503,
        "call_wall": 7247.0, "put_wall": 6997.0,
        "flip": 7288.68, "regime": "negative",
        "net_gex": -4.290e9, "call_gex": 5.935e9,
        "put_gex": -10.225e9,
    }
    data.update(overrides)
    return data


class DualGEXCardTests(unittest.TestCase):
    def test_same_seven_metrics_on_both_independent_dark_cards(self):
        daily = valid_report("2026-11-27")
        weekly = valid_report(
            "2026-12-04", contracts=611, valid=570,
            call_wall=7410.0, put_wall=7010.0,
            flip=7320.51, regime="positive",
            net_gex=1.250e9, call_gex=5.000e9, put_gex=-3.750e9,
        )
        a = _gex_summary_card_html("0DTE", daily, "SPX", 16.0)
        b = _gex_summary_card_html("Weekly", weekly, "SPX", 16.0)

        self.assertIn("0DTE · DAILY", a)
        self.assertIn("WEEKLY", b)
        self.assertIn("Scadenza 2026-11-27", a)
        self.assertIn("Scadenza 2026-12-04", b)
        self.assertIn("Contratti 702", a)
        self.assertIn("Contratti 611", b)
        self.assertIn("7,263.00", a)  # 7247 + 16: solo prezzo ES
        self.assertIn("7,426.00", b)  # 7410 + 16
        self.assertNotIn("7,426.00", a)
        self.assertNotIn("7,263.00", b)
        self.assertIn("7,304.68", a)
        self.assertIn("7,336.51", b)
        self.assertIn("NEGATIVE", a)
        self.assertIn("POSITIVE", b)
        self.assertIn("-4.290", a)
        self.assertIn("+5.935", a)
        self.assertIn("-10.225", a)
        self.assertIn("+1.250", b)
        self.assertIn("+5.000", b)
        self.assertIn("-3.750", b)

        for card in (a, b):
            self.assertIn("background:#090b0f", card)
            self.assertIn("csv-gex-card-grid4", card)
            self.assertIn("csv-gex-card-grid3", card)
            self.assertEqual(card.count('<div class="csv-gex-cell">'), 7)
            self.assertIn("GEX DIAGNOSTICO · NON CERTIFICATO", card)
            for key in ("Call Wall ES", "Put Wall ES", "Gamma Flip ES",
                        "Regime GEX modellato", "NET GEX · mld USD / 1%",
                        "CALL GEX · mld USD / 1%", "PUT GEX · mld USD / 1%"):
                self.assertIn(key, card)

        self.assertIn("csv-gex-value negative", a)
        self.assertIn("color:#ff5967", a)
        self.assertIn("csv-gex-value positive\">POSITIVE", b)
        self.assertIn("color:#18d46d", b)
        self.assertIn("csv-gex-value negative\">NEGATIVE", a)

    def test_positive_regime_uses_cash_calendar_green_for_both_expiries(self):
        for expiry in ("0DTE", "Weekly"):
            with self.subTest(expiry=expiry):
                report = valid_report("2026-11-27", regime="positive")
                card = _gex_summary_card_html(expiry, report, "SPX", 16.0)
                self.assertIn('csv-gex-value positive">POSITIVE', card)
                self.assertIn('.csv-gex-value.positive{color:#18d46d;}', card)
                self.assertNotIn('csv-gex-value negative">POSITIVE', card)
        app = (ROOT / "app.py").read_text(encoding="utf-8")
        self.assertIn("color:#18d46d", app)

    def test_negative_stays_red_unknown_remains_neutral(self):
        red = _gex_summary_card_html(
            "Weekly", valid_report("2026-12-04", regime="negative"),
            "SPX", 16.0,
        )
        self.assertIn('csv-gex-value negative">NEGATIVE', red)
        unknown = _gex_summary_card_html(
            "0DTE", valid_report("2026-11-27", regime=None),
            "SPX", 16.0,
        )
        self.assertIn('csv-gex-value na">N/D', unknown)
        self.assertNotIn('csv-gex-value positive">N/D', unknown)

    def test_no_basis_no_mislabeled_spx_price_as_es(self):
        data = valid_report("2026-11-27")
        html = _gex_summary_card_html("0DTE", data, "SPX", None)
        self.assertIn("Basis ES−SPX N/D", html)
        self.assertNotIn("7,247.00", html)
        self.assertNotIn("7,263.00", html)
        self.assertEqual(html.count('>N/D</div>'), 3)
        self.assertIn("-4.290", html)  # SPX-source GEX unchanged
        self.assertIn("NEGATIVE", html)

    def test_missing_daily_does_not_fabricate_or_reuse_weekly(self):
        invalid = {
            "status": "INSUFFICIENTE", "expiry": "2026-11-26",
            "contracts": 0, "valid": 0,
            "reason": "Scadenza assente dal CSV: nessun livello ipotizzato.",
        }
        html = _gex_summary_card_html("0DTE", invalid, "SPX", 16)
        self.assertIn("GEX NON CALCOLABILE · N/D", html)
        self.assertEqual(html.count('>N/D</div>'), 7)
        self.assertIn("Scadenza assente dal CSV", html)
        weekly = _gex_summary_card_html(
            "Weekly", valid_report("2026-11-27"), "SPX", 16,
        )
        self.assertIn("7,263.00", weekly)
        self.assertNotIn("7,263.00", html)
        missing = _gex_summary_card_html("Weekly", None, "SPX", 16)
        self.assertIn("GEX NON CALCOLABILE · N/D", missing)

    def test_quality_reason_escaped_and_unknown_mode_rejected(self):
        message = "<script>alert('fake')</script>"
        invalid = {
            "status": "INSUFFICIENTE", "expiry": "2026-11-26",
            "reason": message,
        }
        html = _gex_summary_card_html("Weekly", invalid, "SPX", 16)
        self.assertNotIn("<script>", html)
        self.assertIn("&lt;script&gt;", html)
        with self.assertRaises(ValueError):
            _gex_summary_card_html("All", invalid, "SPX", 16)

    def test_non_spx_prices_not_invented_as_es(self):
        html = _gex_summary_card_html(
            "Weekly", valid_report("2026-12-04"), "NDX", None,
        )
        self.assertIn("Call Wall NDX", html)
        self.assertNotIn("Call Wall ES", html)
        self.assertIn("7,247.00", html)
        self.assertNotIn("7,263.00", html)

    def test_layout_only_0dte_charts_after_both_cards(self):
        src = (ROOT / "csv_gex_panel.py").read_text(encoding="utf-8")
        self.assertIn('left, right = st.columns(2, gap="medium")', src)
        self.assertIn('''st.html(_gex_summary_card_html(
            "0DTE", reports.get("0DTE")''', src)
        self.assertIn('''st.html(_gex_summary_card_html(
            "Weekly", reports.get("Weekly")''', src)
        self.assertNotIn('st.radio("Scadenza GEX"', src)
        self.assertIn('key="csv_gex_strikes_0DTE"', src)
        self.assertIn('es_spx_basis=es_spx_basis,selected="0DTE"', src)
        self.assertLess(
            src.index('"Weekly", reports.get("Weekly")'),
            src.index('st.subheader("GEX by Strike'),
        )
        self.assertIn('if report.get("status") != "DIAGNOSTICO":', src)
        self.assertIn("Grafici Daily 0DTE non disponibili", src)
        self.assertIn("i due riquadri NON sono", src)
        self.assertEqual(src.count('st.plotly_chart(\n        strike_fig'), 1)


if __name__ == "__main__":
    unittest.main()
