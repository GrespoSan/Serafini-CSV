import csv
import io
import unittest
from datetime import datetime, timezone
from unittest.mock import Mock
from pathlib import Path
from cboe_csv_import import csv_to_snapshot
from mt4_manual import build_feed, publish, rows100, SOURCE, login_role, ManualStore, published_gex_summary
from net_gamma import profile
from datetime import date

def csv_fixture():
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["S&P 500 INDEX (^SPX)", "Last: 6000.00", "Change: 0.00"])
    writer.writerow(["Date: November 23, 2026, 10:47 AM GMT+1"])
    writer.writerow(["Expiration Date","Calls","Gamma","Volume","Open Interest","Strike","Puts","Gamma","Volume","Open Interest"])
    for day in (date(2026,11,23),date(2026,11,27)):
        for strike in range(5600,6401,5):
            writer.writerow([day.strftime("%a %b %d %Y"),f"SPXW{day:%y%m%d}C{strike*1000:08d}",
                "0.002","10","100",str(strike),f"SPXW{day:%y%m%d}P{strike*1000:08d}","0.002","20","200"])
    return out.getvalue().encode()


class ManualMT4Tests(unittest.TestCase):
    def setUp(self):
        self.doc=csv_to_snapshot(csv_fixture())
        self.now=datetime(2026,11,23,10,0,tzinfo=timezone.utc)
        self.basis={"reference_date":"2026-11-20"}
        self.sha=self.doc["_import_provenance"]["original_csv_sha256"]

    def build(self, saved=None, source=None, now=None):
        return build_feed(self.doc,6000,16,self.basis,source,saved,"",now or self.now)

    def test_manual_morning_and_100_real_strikes(self):
        lines=list(csv.reader(io.StringIO(self.build().decode())))
        meta=dict(r for r in lines if len(r)==2)
        self.assertEqual(meta["snapshot_source"],SOURCE)
        self.assertEqual(meta["snapshot_sha256"],self.sha)
        self.assertEqual(meta["download_clock_rome"],"10:47:00")
        self.assertEqual(meta["mode"],"Manuale")
        self.assertNotIn("gex_model",meta)
        self.assertIsNone(published_gex_summary(self.build()))
        for label,expiry in (("0DTE",date(2026,11,23)),("Weekly",date(2026,11,27))):
            rows=[r for r in lines if r[0]==label]
            self.assertEqual(len(rows),100)
            vals={float(r[2]):float(r[4]) for r in rows}
            self.assertEqual(len(vals),100)
            for row in profile(self.doc,expiry,6000)["rows"]:
                self.assertAlmostEqual(vals[row["strike_spx"]],row["net_gamma"])

    def test_same_csv_gex_only(self):
        source={"sha256":self.sha,"symbol":"SPX","oi_mode":"csv"}
        report={"sha256":self.sha,"symbol":"SPX","source":SOURCE,"quality_certified":False,
            "timestamp_utc":"2026-11-23T09:47:00+00:00","spot_info":{"method":"SPXW_0DTE_PUT_CALL_PARITY_R0_Q0"},"oi_info":{"requested_mode":"csv"},
            "reports":{"0DTE":{"status":"DIAGNOSTICO","expiry":"2026-11-23",
                "net_gex":-2e9,"regime":"negative","call_wall":6100.,"put_wall":5900.,"flip":None},
                "Weekly":{"status":"INSUFFICIENTE"}}}
        saved=((self.sha,"SPX","auto","csv"),report)
        body=self.build(saved,source).decode()
        self.assertIn("gex_call_wall_es,6116.000000",body)
        self.assertIn("gex_modeled_sign,Negative",body)
        self.assertIn("-2,00 mld USD / 1% · Regime NEGATIVO",published_gex_summary(body.encode()))
        self.assertNotIn("gex_gamma_flip_es",body)
        report["reports"]["0DTE"]["regime"]="neutral"
        self.assertIn("gex_modeled_sign,Zero",self.build(saved,source).decode())
        report["spot_info"]={"method":"CSV_LAST"}
        self.assertNotIn("gex_model",self.build(saved,source).decode())
        report["sha256"]="a"*64
        self.assertNotIn("gex_model",self.build(saved,source).decode())

    def test_stale_future_and_unauthorized(self):
        for now in (datetime(2026,11,24,10,tzinfo=timezone.utc),
                    datetime(2026,11,23,9,tzinfo=timezone.utc)):
            with self.assertRaises(ValueError):
                self.build(now=now)
        with self.assertRaises(PermissionError):
            publish(Mock(),self.build(),"friend")

    def test_roles_and_layout(self):
        self.assertEqual(login_role("admin-pass","read-pass","admin-pass"),"admin")
        self.assertEqual(login_role("read-pass","read-pass","admin-pass"),"friend")
        self.assertEqual(login_role("same","same","same"),"friend")
        self.assertEqual(login_role("read-pass","read-pass",None),"friend")
        self.assertIsNone(login_role("wrong","read-pass","admin-pass"))
        text=Path("app.py").read_text()
        self.assertIn('if role == "admin" and asia_panel:',text)
        self.assertIn('publish(target, payload, role)',text)
        self.assertIn('if market == "SP500":',text)
        with self.assertRaises(ValueError):
            ManualStore("https://other.supabase.co","key")

    def test_explicit_publish_and_readback(self):
        from unittest.mock import patch
        target=Mock(url="https://rnpnibdxuqlmuqmcixsd.supabase.co",bucket="spx-snapshots",key="test")
        payload=self.build()
        target._download_uncached.return_value=payload
        with patch("mt4_manual.urlopen") as call:
            call.return_value.__enter__.return_value.status=200
            publish(target,payload,"admin")
            req=call.call_args.args[0]
            self.assertTrue(req.full_url.endswith("/spx-snapshots/mt4/manual100.csv"))
            self.assertEqual(req.data,payload)
            target._download_uncached.assert_called_once_with("mt4/manual100.csv")
            target._download_uncached.return_value=b"wrong"
            with self.assertRaises(RuntimeError):
                publish(target,payload,"admin")

    def test_negative_metrics_style(self):
        for path in ("gamma_section.py","mercati/v2_gamma_summary.py"):
            content=Path(path).read_text()
            self.assertIn("#f05252",content)
            self.assertIn("if value < 0",content)
            self.assertNotIn("put_col.metric(",content)
