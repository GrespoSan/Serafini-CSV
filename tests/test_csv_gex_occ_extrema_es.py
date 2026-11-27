"""No-network GEX OI/ES/extrema regression; preserve Serafini original data."""
from __future__ import annotations

import hashlib
import io
import csv
import json
import math
import unittest
from datetime import date,datetime,timedelta,timezone
from types import SimpleNamespace
from urllib.parse import unquote
from zoneinfo import ZoneInfo

from csv_gex_oi import parse_series,fetch_occ_oi,apply_mode,OiSourceError
from csv_gex_es_quote import front_symbol,parse_chart,fetch_es_quote
from csv_gex_curve import curve_extrema, quote_inside_curve
from csv_gex_engine import analyze_csv_gex
from cboe_csv_import import csv_to_snapshot

NY=ZoneInfo("America/New_York")


def sample_csv(day="2026-11-23"):
    # Explicit same-day timestamp and existing Cboe CSV schema.
    out=io.StringIO(newline="")
    w=csv.writer(out)
    w.writerow(["S&P 500 INDEX (^SPX)","Last: 100.00","Change: +0.5"])
    dt=datetime.fromisoformat(day).strftime("%B %-d, %Y")
    w.writerow([f"Date: {dt}, 10:00 AM EST"])
    w.writerow(["Expiration Date","Calls","Gamma","Volume","Open Interest","IV",
                "Strike","Puts","Gamma","Volume","Open Interest","IV"])
    for expiry in ("261123","261127"):
        for strike in range(88,113):
            w.writerow(["Cboe",f"SPXW{expiry}C{strike*1000:08d}",".009","12",
                        "500",".22",str(strike),
                        f"SPXW{expiry}P{strike*1000:08d}",".009","7","350",".26"])
    return out.getvalue().encode()


class SourceTests(unittest.TestCase):
    def contracts(self):
        expiries={"0DTE":date(2026,11,23),"Weekly":date(2026,11,27)}
        rows=[]
        for expiry in expiries.values():
            for n in range(25):
                for side in ("C","P"):
                    code=f"SPXW{expiry:%y%m%d}{side}{(100+n)*1000:08d}"
                    rows.append(SimpleNamespace(symbol=code,expiry=expiry,
                                                strike=100+n,oi=100,
                                                oi_source="cboe_csv",oi_date=None))
        return rows,expiries

    def test_parser_exact_occ_names_and_zero_unknown(self):
        c="SPXW261123C06900000"
        p="SPXW261123P06900000"
        a="SPXW261123C06905000"
        text=("Series Search Results\n"
              "SPXW 2026 11 23 6900 000 C P 20 30 0\n"
              "SPXW 2026 11 23 6905 000 C P 0 45 0\n")
        mapping=parse_series(text,accepted={c,p,a,"SPXW261123P06906000"})
        self.assertEqual(mapping,{c:20,p:30,a:0})
        self.assertNotIn("SPXW261123P06906000",mapping)

    def test_fetch_records_download_time_not_fake_oi_vintage(self):
        key="SPXW261123C06900000"
        data=b"Series Search Results\nSPXW 2026 11 23 6900 000 C P 0 1 0\n"
        now=datetime(2026,11,23,19,5,tzinfo=timezone.utc)
        record,meta=fetch_occ_oi("SPX",{key},request=lambda url:data,clock=now)
        self.assertEqual(record[key],0)
        self.assertEqual(meta["download_utc"],now.isoformat())
        self.assertIsNone(meta["oi_asof_date"])
        self.assertEqual(meta["oi_asof_status"],"NON_PUBBLICATA_NEL_REPORT")

    def test_bad_occ_response_never_falls_to_zero(self):
        with self.assertRaises(OiSourceError):
            fetch_occ_oi("SPX",{"SPXW261123C06900000"},
                         request=lambda url:b"<html>denied</html>")

    def test_mode_csv_preserved_and_occ_only_changes_all_rows(self):
        rows,expiries=self.contracts()
        now=datetime.now(timezone.utc)
        captured=now.astimezone(NY)
        occ={x.symbol:201 for x in rows}
        meta={"source":"OCC_SERIES_SEARCH","download_utc":now.isoformat()}
        csv_rows,csv_info=apply_mode(rows,mode="csv",captured=captured,
            target_expiries=expiries,spot=107,occ=None,provenance=None)
        self.assertEqual(csv_rows[0].oi,100)
        self.assertEqual(csv_info["effective_source"],"CSV_CBOE")
        new,info=apply_mode(rows,mode="occ",captured=captured,
            target_expiries=expiries,spot=107,occ=occ,provenance=meta)
        self.assertEqual(rows[0].oi,100)
        self.assertEqual(new[0].oi,201)
        self.assertEqual(new[0].oi_source,"occ_series_search")
        self.assertTrue(all(x.oi_date is None for x in new))
        self.assertFalse(info["mixed_sources"])
        self.assertEqual(info["effective_source"],"OCC_SERIES_SEARCH")

    def test_auto_fallback_is_explicit_and_occ_only_blocks(self):
        rows,expiries=self.contracts()
        now=datetime.now(timezone.utc)
        args=dict(captured=now.astimezone(NY),target_expiries=expiries,
                  spot=107,occ={},provenance={
                   "source":"OCC_SERIES_SEARCH","download_utc":now.isoformat()})
        new,info=apply_mode(rows,mode="auto",**args)
        self.assertEqual([r.oi for r in new],[100]*len(rows))
        self.assertTrue(info["fallback_reason"])
        with self.assertRaises(OiSourceError):
            apply_mode(rows,mode="occ",**args)

    def test_no_old_csv_overwritten_by_new_occ(self):
        rows,expiries=self.contracts()
        now=datetime.now(timezone.utc)
        old=now-timedelta(days=6)
        occ={x.symbol:777 for x in rows}
        meta={"source":"OCC_SERIES_SEARCH","download_utc":now.isoformat()}
        new,info=apply_mode(rows,mode="auto",captured=old,target_expiries=expiries,
                            spot=107,occ=occ,provenance=meta)
        self.assertEqual(new[0].oi,100)
        self.assertIn("storico",info["fallback_reason"])
        with self.assertRaises(OiSourceError):
            apply_mode(rows,mode="occ",captured=old,target_expiries=expiries,
                       spot=107,occ=occ,provenance=meta)

    def test_extrema_positive_and_negative_gex_at_actual_es_price(self):
        rows=[{"spot":100,"net_gex":-7.3e9},
              {"spot":101,"net_gex":8.2e9},
              {"spot":102,"net_gex":1.0e9}]
        result=curve_extrema({"curve":rows},symbol="SPX",es_spx_basis=17)
        self.assertEqual(result["maximum"],{"price":118,"gex":8.2e9})
        self.assertEqual(result["minimum"],{"price":117,"gex":-7.3e9})
        self.assertIsNone(curve_extrema({"curve":rows},symbol="SPX"))

    def test_actual_es_outside_historical_curve_is_not_plotted(self):
        report={"curve":[{"spot":100,"net_gex":-1e9},
                         {"spot":101,"net_gex":2e9},
                         {"spot":102,"net_gex":1e9}]}
        self.assertFalse(quote_inside_curve(report,{"price":7260},
                         symbol="SPX",es_spx_basis=17))
        self.assertTrue(quote_inside_curve(report,{"price":118},
                         symbol="SPX",es_spx_basis=17))
        self.assertFalse(quote_inside_curve(report,{"price":118},
                         symbol="SPX",es_spx_basis=None))

    def test_es_contract_and_quote_clock_with_fallback(self):
        self.assertEqual(front_symbol(date(2026,11,23)),"ESZ26.CME")
        now=datetime(2026,11,23,21,0,tzinfo=timezone.utc)
        source_t=now-timedelta(minutes=15)
        source=json.dumps({"chart":{"result":[{
            "meta":{"symbol":"ESZ26.CME"},
            "timestamp":[int(source_t.timestamp())],
            "indicators":{"quote":[{"close":[7265.75]}]},
        }]}}).encode()
        result=fetch_es_quote(now=now,request=lambda url:source)
        self.assertEqual(result["price"],7265.75)
        self.assertEqual(result["symbol"],"ESZ26.CME")
        self.assertEqual(result["age_minutes"],15.0)
        stale=json.dumps({"chart":{"result":[{
            "timestamp":[int((now-timedelta(hours=5)).timestamp())],
            "indicators":{"quote":[{"close":[7250.0]}]},
        }]}}).encode()
        self.assertIsNone(fetch_es_quote(now=now,request=lambda url:stale)["price"])

    def test_es_f_continuous_fallback_must_be_labeled(self):
        now=datetime(2026,11,23,21,0,tzinfo=timezone.utc)
        timestamp=int((now-timedelta(minutes=8)).timestamp())
        doc=json.dumps({"chart":{"result":[{
            "meta":{"symbol":"ES=F"},"timestamp":[timestamp],
            "indicators":{"quote":[{"close":[7292.25]}]},
        }]}}).encode()
        def request(url):
            if "ESZ26.CME" in unquote(url):
                raise ValueError("Not available")
            return doc
        result=fetch_es_quote(now=now,request=request)
        self.assertEqual(result["contract_kind"],"CONTINUOUS")
        self.assertEqual(result["symbol"],"ES=F")
        self.assertEqual(result["price"],7292.25)

    def test_yahoo_query2_fallback_when_query1_blocked(self):
        # Simula un blocco di query1 (p.es. HTTP 429 da cloud):
        # la stessa quotazione Yahoo deve essere recuperata su query2.
        now = datetime(2026, 11, 27, 7, 30, tzinfo=timezone.utc)
        tick = int((now - timedelta(minutes=11)).timestamp())
        doc = json.dumps({"chart": {"result": [{
            "meta": {"symbol": "ES=F"}, "timestamp": [tick],
            "indicators": {"quote": [{"close": [7318.25]}]},
        }]}}).encode()
        calls = []
        def simulated_request(url):
            calls.append(url)
            if "query1.finance.yahoo.com" in url:
                raise ValueError("Rate limited")
            if "ESZ26.CME" in unquote(url):
                raise ValueError("Contratto esplicito non disponibile")
            return doc

        result = fetch_es_quote(now=now, request=simulated_request)
        self.assertEqual(result["price"], 7318.25)
        self.assertEqual(result["age_minutes"], 11.0)
        self.assertEqual(result["symbol"], "ES=F")
        self.assertEqual(result["contract_kind"], "CONTINUOUS")
        self.assertEqual(result["source"], "YAHOO_FINANCE_CHART")
        self.assertTrue(any("query2.finance.yahoo.com" in x for x in calls))
        self.assertTrue(all("range=2d&interval=1m" in x for x in calls))

    def test_query2_cannot_bypass_90_minute_limit(self):
        now = datetime(2026, 11, 27, 7, 30, tzinfo=timezone.utc)
        old_tick = int((now - timedelta(minutes=93)).timestamp())
        stale = json.dumps({"chart": {"result": [{
            "meta": {"symbol": "ES=F"}, "timestamp": [old_tick],
            "indicators": {"quote": [{"close": [7290.75]}]},
        }]}}).encode()
        result = fetch_es_quote(now=now, request=lambda url: stale)
        self.assertIsNone(result["price"])
        self.assertIn("Nessuna quotazione ES utilizzabile", result["error"])
        self.assertIn("query2.finance.yahoo.com", result["error"])

    def test_engine_csv_default_unaffected_by_occ_module(self):
        # Existing engine path uses the unmodified CSV OI by default.
        from tests.test_csv_gex_integration import fixture
        blob=fixture()
        a=analyze_csv_gex(blob,"NVDA")
        b=analyze_csv_gex(blob,"NVDA",oi_mode="csv")
        for expiry in ("0DTE","Weekly"):
            self.assertEqual(a["reports"][expiry]["flip"],b["reports"][expiry]["flip"])
            self.assertEqual(a["reports"][expiry]["net_gex"],b["reports"][expiry]["net_gex"])
        self.assertEqual(a["oi_info"]["effective_source"],"CSV_CBOE")


if __name__=="__main__":
    unittest.main()
