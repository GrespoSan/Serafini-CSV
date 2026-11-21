"""Pine GEX CSV: link fonte, controlli qualità e isolamento matematico."""
import copy
import unittest

from csv_gex_pine import (
    MODE_BY_LABEL, validate_result, append_csv_gex,
)

SHA = "ab" * 32
BASE = (
    '//@version=6\n'
    'indicator("Serafini NET GAMMA", overlay=true, max_lines_count=500)\n'
    'validTicker = syminfo.type == "futures" and syminfo.root == "ES"\n'
    'var array<float> netGammaOriginal = array.from(10.0, -20.0)\n'
)


def fixture(*, only="both", flip=True):
    a = {
        "mode": "0DTE", "expiry": "2026-11-20", "status": "DIAGNOSTICO",
        "quality_certified": False, "call_wall": 102.25,
        "put_wall": 97.5, "flip": 100.5 if flip else None,
        "regime": "positive",
    }
    b = {
        "mode": "Weekly", "expiry": "2026-11-27", "status": "DIAGNOSTICO",
        "quality_certified": False, "call_wall": 110.0,
        "put_wall": 90.0, "flip": 99.0, "regime": "negative",
    }
    if only == "0DTE":
        b.update(status="INSUFFICIENTE", call_wall=None, put_wall=None, flip=None)
    if only == "none":
        a.update(status="INSUFFICIENTE", call_wall=None, put_wall=None, flip=None)
        b.update(status="INSUFFICIENTE", call_wall=None, put_wall=None, flip=None)
    report = {
        "sha256": SHA, "symbol": "SPX", "source": "CBOE_CSV_MANUAL_USER_EXPORT",
        "quality_certified": False, "timestamp_rome": "20/11/2026 16:45:00",
        "reports": {"0DTE": a, "Weekly": b},
    }
    saved = ((SHA, "SPX", "decimal"), report)
    return saved, {"sha256": SHA, "symbol": "SPX"}


class GexCSVExportTests(unittest.TestCase):
    def test_match_and_both_expiries(self):
        saved, source = fixture()
        report, allowed = validate_result(saved, source, "decimal")
        self.assertEqual(set(allowed), {"0DTE", "Weekly"})
        result = append_csv_gex(BASE, report, allowed)
        self.assertTrue(result.startswith(BASE))
        self.assertIn("var array<float> netGammaOriginal = array.from(10.0, -20.0)", result)
        self.assertIn("float _csvGex0Call = 102.25000000", result)
        self.assertIn("float _csvGexWPut = 90.00000000", result)
        self.assertIn('input.bool(true, "Mostra GEX 0DTE"', result)
        self.assertIn('input.bool(false, "Mostra GEX Weekly"', result)
        self.assertIn('if validTicker', result)
        self.assertIn(SHA[:16], result)
        self.assertIn("non livelli operativi certificati", result)

    def test_basis_es_nq_rty_and_djx(self):
        saved, source = fixture(only="0DTE")
        report, allowed = validate_result(saved, source, "decimal")
        projected = append_csv_gex(BASE, report, allowed, price_factor=100.0, price_shift=40.0)
        self.assertIn("float _csvGex0Call = 10265.00000000", projected)
        self.assertIn("float _csvGex0Put = 9790.00000000", projected)
        self.assertNotIn("float _csvGexWCall", projected)
        self.assertIn("Weekly: qualità insufficiente", projected)

    def test_ratio_gld_uso(self):
        saved, source = fixture(only="0DTE")
        report, allowed = validate_result(saved, source, "decimal")
        projected = append_csv_gex(BASE, report, allowed, price_factor=10.0)
        self.assertIn("float _csvGex0Call = 1022.50000000", projected)

    def test_no_gamma_flip_means_no_line(self):
        saved, source = fixture(only="0DTE", flip=False)
        report, allowed = validate_result(saved, source, "decimal")
        output = append_csv_gex(BASE, report, allowed)
        self.assertIn("float _csvGex0Flip = na", output)
        self.assertNotIn('label lb = label.new(bar_index, _csvGex0Flip', output)

    def test_mismatched_source_mode_symbol_all_rejected(self):
        saved, source = fixture()
        for modified in (
            {"sha256": "cd" * 32, "symbol": "SPX"},
            {"sha256": SHA, "symbol": "NDX"},
        ):
            with self.assertRaises(ValueError):
                validate_result(saved, modified, "decimal")
        with self.assertRaises(ValueError):
            validate_result(saved, source, "percent")
        with self.assertRaises(ValueError):
            validate_result(None, source, "decimal")
        self.assertEqual(MODE_BY_LABEL["IV decimale · 0,20 = 20%"], "decimal")

    def test_no_levels_when_all_insufficient(self):
        saved, source = fixture(only="none")
        with self.assertRaisesRegex(ValueError, "qualità diagnostica"):
            validate_result(saved, source, "decimal")

    def test_wrong_quality_or_source_rejected(self):
        saved, source = fixture()
        for key, value in (("quality_certified", True), ("source", "ALPACA"),
                           ("symbol", "NDX")):
            changed = copy.deepcopy(saved)
            changed[1][key] = value
            with self.assertRaises(ValueError):
                validate_result(changed, source, "decimal")
        report, allowed = validate_result(saved, source, "decimal")
        allowed["0DTE"]["quality_certified"] = True
        with self.assertRaisesRegex(ValueError, "Qualità"):
            append_csv_gex(BASE, report, allowed)

    def test_reject_duplicate_or_forged_price_and_no_guard(self):
        saved, source = fixture()
        report, allowed = validate_result(saved, source, "decimal")
        result = append_csv_gex(BASE, report, allowed)
        with self.assertRaisesRegex(ValueError, "già"):
            append_csv_gex(result, report, allowed)
        with self.assertRaises(ValueError):
            append_csv_gex(BASE, report, allowed, price_factor=0)
        with self.assertRaises(ValueError):
            append_csv_gex(BASE, report, allowed, price_shift=float("nan"))
        with self.assertRaises(ValueError):
            append_csv_gex('//@version=6\nindicator("Bad")', report, allowed)

    def test_source_cannot_insert_pine(self):
        saved, source = fixture()
        report, allowed = validate_result(saved, source, "decimal")
        report["timestamp_rome"] = '20/11/2026 16:45:00"\nplot(close)'
        with self.assertRaisesRegex(ValueError, "Timestamp"):
            append_csv_gex(BASE, report, allowed)


if __name__ == "__main__":
    unittest.main()
