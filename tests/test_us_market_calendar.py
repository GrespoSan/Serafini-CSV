"""Calendario CONTEXTO cash USA: festività, chiusure e no falsi segnali.

I dati dello snapshot GEX/NET GAMMA non devono modificare l'avviso odierno:
si usa sempre il calendario ufficiale delle sedute XNYS, senza rete.
"""
from datetime import date
from pathlib import Path
from unittest.mock import patch
import unittest

from us_market_calendar import (
    nyse_day_status, NYSE_SOURCE, CBOE_SOURCE, CME_SOURCE,
)


ROOT = Path(__file__).resolve().parents[1]


class NYSEHolidayContextTests(unittest.TestCase):
    def test_thanksgiving_2026_is_cash_closed_not_all_markets_closed(self):
        info = nyse_day_status(date(2026, 11, 26))
        self.assertEqual(info["status"], "holiday")
        self.assertEqual(info["holiday"], "Thanksgiving")
        self.assertIn("FESTIVITÀ USA", info["title"])
        self.assertIn("NYSE", info["detail"])
        self.assertIn("NON implica", info["detail"])
        self.assertEqual(info["source"], NYSE_SOURCE)
        self.assertTrue(info["cash_only"])

    def test_black_friday_2026_early_close_converted_to_rome(self):
        info = nyse_day_status(date(2026, 11, 27))
        self.assertEqual(info["status"], "early_close")
        self.assertEqual(info["close_ny"], "13:00")
        self.assertEqual(info["close_rome"], "19:00")
        self.assertIn("19:00 Roma", info["detail"])

    def test_non_holiday_wednesday_remains_regular(self):
        info = nyse_day_status(date(2026, 11, 25))
        self.assertEqual(info["status"], "regular")
        self.assertEqual(info["detail"], "")

    def test_weekend_is_not_misnamed_holiday(self):
        info = nyse_day_status(date(2026, 11, 28))
        self.assertEqual(info["status"], "weekend")
        self.assertNotIn("FESTIVITÀ", info["title"])

    def test_christmas_and_good_friday_have_calendar_verified_names(self):
        for day, expected in (
            (date(2026, 12, 25), "Natale"),
            (date(2027, 3, 26), "Good Friday"),
        ):
            with self.subTest(day=day):
                info = nyse_day_status(day)
                self.assertEqual(info["status"], "holiday")
                self.assertIn(expected, info["holiday"])

    def test_calendar_error_never_claims_market_open_or_closed(self):
        with patch("us_market_calendar.xcals.get_calendar",
                   side_effect=ValueError("Out of calendar range")):
            info = nyse_day_status(date(2026, 11, 26))
        self.assertEqual(info["status"], "unknown")
        self.assertIn("impossibile accertare", info["detail"].lower())

    def test_invalid_day_not_silently_interpreted_as_today(self):
        with self.assertRaises(TypeError):
            nyse_day_status("2026-11-26")

    def test_app_shows_warning_in_context_title_even_when_collapsed(self):
        app = (ROOT / "app.py").read_text(encoding="utf-8")
        self.assertIn("nyse_status = today_rome_market_status()", app)
        self.assertIn('context_suffix = " · 🇺🇸 FESTIVITÀ USA — CASH CHIUSO"', app)
        self.assertIn('context_suffix = " · 🇺🇸 CHIUSURA ANTICIPATA CASH"', app)
        self.assertIn('if nyse_status["status"] in ("holiday", "early_close"):', app)
        self.assertIn('<div style="padding:6px 0 12px 0;">', app)
        self.assertIn('border-radius:999px;background:#0d3020', app)
        self.assertIn('color:#18d46d', app)
        self.assertIn('&#10003;', app)
        self.assertIn('color:#d1d5db', app)
        self.assertIn('escape(nyse_status["detail"])', app)
        self.assertNotIn('''        st.warning(
            f"**{nyse_status['title']} — {nyse_status['day']}**''', app)
        self.assertIn('f"[NYSE]({NYSE_SOURCE})', app)
        self.assertIn('f"[Cboe SPX]({CBOE_SOURCE})', app)
        self.assertIn('f"[CME futures ES]({CME_SOURCE})', app)
        self.assertLess(app.index("nyse_status = today_rome_market_status()"),
                        app.index('with st.expander(\n    "ANALISI DEL CONTESTO'))
        self.assertIn('render_trend_daily(reference_day=trend_day', app)
        self.assertIn('render_csv_gex(', app)
        self.assertIn('asia_panel = render(store,', app)
        self.assertTrue(all(s.startswith("https://") for s in (
            NYSE_SOURCE, CBOE_SOURCE, CME_SOURCE,
        )))


if __name__ == "__main__":
    unittest.main()
