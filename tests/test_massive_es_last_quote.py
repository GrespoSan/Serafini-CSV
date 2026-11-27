"""Test ES quotazioni: Yahoo prioritario; Massive 5m solo se autorizzato.

Verifiche offline: non richiedono chiavi, Internet né prezzi inventati.
"""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import unittest

from csv_gex_quote_cache import resolve_es_quote
from massive_es_last_quote import parse_massive_es_5min, fetch_massive_es_quote
from gamma_es_quote_overlay import add_es_quote_to_net_gamma
import plotly.graph_objects as go

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 11, 27, 8, 35, tzinfo=timezone.utc)
CONTRACT = "ESZ6"


def bar(*, age_min=11, ticker=CONTRACT, close=7309.25):
    """Massive window_start is nanoseconds; close time is start + 5m."""
    start = NOW - timedelta(minutes=age_min + 5)
    return {
        "window_start": int(start.timestamp() * 1_000_000_000),
        "ticker": ticker,
        "open": close - 1, "high": close + 2,
        "low": close - 2, "close": close,
    }


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class ESQuoteFallbackTests(unittest.TestCase):
    def test_massive_5min_bar_time_is_close_not_download(self):
        quote = parse_massive_es_5min(
            {"status": "DELAYED", "results": [bar()]},
            contract=CONTRACT, now=NOW,
        )
        self.assertEqual(quote["price"], 7309.25)
        self.assertEqual(quote["symbol"], "ESZ6")
        self.assertEqual(quote["source"], "MASSIVE_FUTURES_5MIN")
        self.assertEqual(quote["age_minutes"], 11.0)
        self.assertEqual(quote["provider_status"], "DELAYED")
        self.assertIn("09:24:00", quote["observed_rome"])
        self.assertIn("ultima barra ES 5m chiusa", quote["delayed_label"])

    def test_freshest_valid_completed_bar_selected(self):
        newer = bar(age_min=6, close=7310.50)
        too_new = bar(age_min=-3, close=9999.0)
        older = bar(age_min=75, close=7280.50)
        q = parse_massive_es_5min(
            {"status": "OK", "results": [older, too_new, newer]},
            contract=CONTRACT, now=NOW,
        )
        self.assertEqual(q["price"], 7310.50)
        self.assertEqual(q["age_minutes"], 6)

    def test_old_bar_or_non_finite_is_not_plotted(self):
        for rows in ([bar(age_min=91)], [bar(close=float("nan"))], []):
            with self.subTest(rows=rows):
                with self.assertRaises(ValueError):
                    parse_massive_es_5min(
                        {"status": "DELAYED", "results": rows},
                        contract=CONTRACT, now=NOW,
                    )

    def test_wrong_contract_and_incomplete_page_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "contratto diverso"):
            parse_massive_es_5min(
                {"status": "OK", "results": [bar(ticker="ESH7")]},
                contract=CONTRACT, now=NOW,
            )
        with self.assertRaisesRegex(ValueError, "risposta incompleta"):
            parse_massive_es_5min(
                {"status": "OK", "results": [bar()], "next_url": "more"},
                contract=CONTRACT, now=NOW,
            )

    def test_http_uses_existing_contract_and_secret_not_in_output(self):
        captured = []
        def get(url, **kwargs):
            captured.append((url, kwargs))
            return FakeResponse({"status": "DELAYED", "results": [bar()]})
        quote = fetch_massive_es_quote(
            api_key="secret-key", now=NOW, get=get,
        )
        self.assertEqual(quote["price"], 7309.25)
        self.assertEqual(len(captured), 1)
        self.assertTrue(captured[0][0].endswith("/ESZ6"))
        self.assertEqual(captured[0][1]["params"]["resolution"], "5min")
        self.assertEqual(captured[0][1]["headers"]["Authorization"],
                         "Bearer secret-key")
        self.assertNotIn("secret-key", str(quote))
        with self.assertRaisesRegex(ValueError, "MASSIVE_API_KEY"):
            fetch_massive_es_quote(api_key="", now=NOW, get=get)
        self.assertEqual(len(captured), 1)

    def test_yahoo_preferred_when_both_have_valid_quote(self):
        calls = []
        result = resolve_es_quote(
            lambda: {"price": 7311.50, "source": "YAHOO_FINANCE_CHART"},
            lambda **kw: calls.append(kw), "secret",
        )
        self.assertEqual(result["price"], 7311.50)
        self.assertFalse(calls)

    def test_if_yahoo_missing_use_massive_with_verifiable_5m(self):
        quote = parse_massive_es_5min(
            {"status": "DELAYED", "results": [bar()]},
            contract=CONTRACT, now=NOW,
        )
        result = resolve_es_quote(
            lambda: {"price": None, "error": "Rate limited"},
            lambda **kw: quote, "preexisting-secret",
        )
        self.assertEqual(result["source"], "MASSIVE_FUTURES_5MIN")
        self.assertEqual(result["price"], 7309.25)

    def test_no_entitlement_or_missing_key_does_not_fabricate(self):
        def denied(**kw):
            raise ValueError("Massive Futures: no entitlement")
        for key in ("", "secret"):
            quote = resolve_es_quote(
                lambda: {"price": None, "error": "Yahoo denied"}, denied, key,
            )
            self.assertIsNone(quote["price"])
            self.assertIn("Yahoo denied", quote["error"])
            self.assertIn("Massive", quote["error"])
            self.assertNotIn("secret", quote["error"])

    def test_chart_overlay_accepts_only_verified_recent_massive(self):
        quote = parse_massive_es_5min(
            {"status": "DELAYED", "results": [bar()]},
            contract=CONTRACT, now=NOW,
        )
        fig = go.Figure(go.Bar(
            x=[-1.5, 0.5], y=[7300, 7330], orientation="h"
        ))
        result = add_es_quote_to_net_gamma(
            fig, [7300, 7330], quote, has_es_axis=True,
        )
        self.assertTrue(result["shown"])
        self.assertIn("Massive 5m", fig.layout.annotations[0].text)
        self.assertEqual(result["source"], "MASSIVE_FUTURES_5MIN")

    def test_gex_price_label_and_source_explicit_in_ui(self):
        panel = (ROOT / "csv_gex_panel.py").read_text(encoding="utf-8")
        net = (ROOT / "gamma_section.py").read_text(encoding="utf-8")
        self.assertIn("Massive 5m", panel)
        self.assertIn("Massive Futures · ultima barra 5m chiusa", panel)
        self.assertIn("Massive Futures · barra 5m chiusa", net)
        self.assertIn("ES Yahoo/Massive", panel)
        self.assertIn("Diagnostica fonti prezzo ES", panel)
        self.assertIn("Diagnostica fonti prezzo ES", net)


if __name__ == "__main__":
    unittest.main()
