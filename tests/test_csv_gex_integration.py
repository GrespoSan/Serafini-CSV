"""GEX CSV regressions: source, model, quality gates, expiry, no fabrication."""
import csv
import io
import math
import unittest

from csv_gex_core.bsm import gamma
from csv_gex_core.gex import contract_gex, zero_crossings
from csv_gex_engine import analyze_csv_gex, _raw_field_presence, _iv_normalization
from cboe_csv_import import csv_to_snapshot


def fixture(*, include_weekly=True, iv="0.20", oi_call="300", oi_put="150"):
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(["NVIDIA CORPORATION (NVDA)", "Last: 100.00", "Change: +0.50"])
    writer.writerow(["Date: November 20, 2026, 9:00 AM EST"])
    writer.writerow([
        "Expiration Date", "Calls", "Gamma", "Volume", "Open Interest", "IV",
        "Strike", "Puts", "Gamma", "Volume", "Open Interest", "IV",
    ])
    for expiry in ("261120", "261127") if include_weekly else ("261120",):
        for strike in range(88, 113):
            code = f"{strike * 1000:08d}"
            writer.writerow([
                "Cboe", f"NVDA{expiry}C{code}", "0.009", "10",
                oi_call, iv, f"{strike:.2f}",
                f"NVDA{expiry}P{code}", "0.009", "10",
                oi_put, iv,
            ])
    return output.getvalue().encode("utf-8")


class GEXCSVTests(unittest.TestCase):
    def test_model_goldens_from_original_edge(self):
        expected_gamma = 0.0198476273738505
        self.assertAlmostEqual(gamma(100, 100, 1.0, 0, .2), expected_gamma, places=12)
        self.assertAlmostEqual(
            contract_gex(expected_gamma, 1000, 100, 100.0, 1),
            198476.273738505, places=5,
        )
        self.assertAlmostEqual(
            contract_gex(expected_gamma, 1000, 100, 100.0, -1),
            -198476.273738505, places=5,
        )

    def test_0dte_weekly_diagnostic_two_independent_expiries(self):
        result = analyze_csv_gex(fixture(), "NVDA")
        self.assertEqual(result["source"], "CBOE_CSV_MANUAL_USER_EXPORT")
        self.assertFalse(result["quality_certified"])
        self.assertEqual(result["iv_unit"], "decimal")
        a, b = result["reports"]["0DTE"], result["reports"]["Weekly"]
        self.assertEqual(a["expiry"], "2026-11-20")
        self.assertEqual(b["expiry"], "2026-11-27")
        self.assertEqual(a["status"], "DIAGNOSTICO")
        self.assertEqual(b["status"], "DIAGNOSTICO")
        for report in (a, b):
            self.assertEqual(len(report["curve"]), 201)
            self.assertIsNotNone(report["call_wall"])
            self.assertIsNotNone(report["put_wall"])
            self.assertGreater(report["net_gex"], 0)
            self.assertEqual(report["regime"], "positive")
            self.assertFalse(report["quality_certified"])
            self.assertTrue(math.isclose(
                report["net_gex"], report["call_gex"] + report["put_gex"],
                rel_tol=1e-9, abs_tol=0.01,
            ))
            self.assertTrue(all(math.isfinite(r["net_gex"]) for r in report["curve"]))

    def test_missing_weekly_is_not_fabricated(self):
        result = analyze_csv_gex(fixture(include_weekly=False), "NVDA")
        weekly = result["reports"]["Weekly"]
        self.assertEqual(weekly["status"], "INSUFFICIENTE")
        self.assertIsNone(weekly["call_wall"])
        self.assertEqual(weekly["curve"], [])
        self.assertIsNone(weekly["net_gex"])

    def test_missing_iv_must_fail_closed(self):
        result = analyze_csv_gex(fixture(iv=""), "NVDA")
        self.assertIsNone(result["iv_unit"])
        for report in result["reports"].values():
            self.assertEqual(report["status"], "INSUFFICIENTE")
            self.assertIsNone(report["flip"])
            self.assertEqual(report["curve"], [])

    def test_missing_oi_not_silent_zero(self):
        blob = fixture(oi_call="", oi_put="")
        doc = csv_to_snapshot(blob, "NVDA")
        presence = _raw_field_presence(
            blob, {x["option"] for x in doc["data"]["options"]},
        )
        self.assertFalse(presence["NVDA261120C00088000"]["oi"])
        result = analyze_csv_gex(blob, "NVDA")
        self.assertEqual(result["oi_missing"], 100)
        self.assertTrue(all(r["status"] == "INSUFFICIENTE" for r in result["reports"].values()))

    def test_iv_units_must_not_be_guessed_if_ambiguous(self):
        blob = fixture(iv="4.5")
        result = analyze_csv_gex(blob, "NVDA")
        self.assertIsNone(result["iv_unit"])
        self.assertEqual(result["reports"]["0DTE"]["status"], "INSUFFICIENTE")

    def test_percentage_iv_explicit_and_auto_are_equivalent(self):
        blob = fixture(iv="20")
        auto = analyze_csv_gex(blob, "NVDA", "auto")
        explicit = analyze_csv_gex(blob, "NVDA", "percent")
        self.assertEqual(auto["iv_unit"], "percent")
        self.assertAlmostEqual(
            auto["reports"]["0DTE"]["net_gex"],
            explicit["reports"]["0DTE"]["net_gex"],
            places=6,
        )

    def test_flip_not_invented_if_no_sign_change(self):
        import numpy as np
        grid = np.array([90.0, 95.0, 100.0, 105.0, 110.0])
        self.assertEqual(zero_crossings(grid, np.ones(5)), [])

    def test_spx_occ_weekly_roots_use_same_engine(self):
        source = fixture()
        source = source.replace(b"9:00 AM EST", b"10:00 AM EST")
        source = source.replace(b"NVIDIA CORPORATION (NVDA)",
                                b"S&P 500 INDEX (^SPX)").replace(b"NVDA", b"SPXW")
        result = analyze_csv_gex(source, "SPX")
        self.assertEqual(result["reports"]["0DTE"]["status"], "DIAGNOSTICO")
        self.assertEqual(result["reports"]["Weekly"]["status"], "DIAGNOSTICO")
        self.assertEqual(result["reports"]["0DTE"]["expiry"], "2026-11-20")

    def test_after_market_close_does_not_backfill_expired_0dte(self):
        source = fixture().replace(b"9:00 AM EST", b"5:00 PM EST")
        result = analyze_csv_gex(source, "NVDA")
        self.assertEqual(result["reports"]["0DTE"]["expiry"], "2026-11-23")
        self.assertEqual(result["reports"]["0DTE"]["status"], "INSUFFICIENTE")
        self.assertIsNone(result["reports"]["0DTE"]["call_wall"])
        self.assertEqual(result["reports"]["Weekly"]["expiry"], "2026-11-27")

    def test_december_only_spx_csv_explains_missing_november_0dte(self):
        # 27 novembre 2026, ore 03:03 New York (pre-USA): la catena
        # contiene esclusivamente scadenze di dicembre. Nessuna
        # parità 0DTE può essere usata per validare lo SPX implicito.
        source = fixture()
        source = source.replace(
            b"November 20, 2026, 9:00 AM EST",
            b"November 27, 2026, 3:03 AM EST",
        )
        source = source.replace(b"261120", b"261201")
        source = source.replace(b"261127", b"261204")
        source = source.replace(
            b"NVIDIA CORPORATION (NVDA)", b"S&P 500 INDEX (^SPX)"
        ).replace(b"NVDA", b"SPXW")
        with self.assertRaisesRegex(
            ValueError,
            r"0DTE richiesta \(2026-11-27\).*non è presente nel CSV",
        ) as ctx:
            analyze_csv_gex(source, "SPX")
        self.assertIn("2026-12-01", str(ctx.exception))
        self.assertIn("2026-12-04", str(ctx.exception))
        self.assertNotIn("meno di 10 coppie", str(ctx.exception))

    def test_future_forged_csv_time_refused(self):
        source = fixture().replace(b"November 20, 2026", b"November 20, 2099")
        with self.assertRaisesRegex(ValueError, "data futura"):
            analyze_csv_gex(source, "NVDA")

    def test_wrong_symbol_rejected_by_existing_parser(self):
        from cboe_csv_import import InvalidCboeCSV
        with self.assertRaises(InvalidCboeCSV):
            analyze_csv_gex(fixture(), "AAPL")


if __name__ == "__main__":
    unittest.main()
