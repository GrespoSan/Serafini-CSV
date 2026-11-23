"""Regressioni riconoscimento IV Cboe: catena ampia e outlier lontani."""
import unittest
from datetime import date

from csv_gex_engine import _iv_normalization


EXP = date(2026, 11, 23)
WEEKLY = date(2026, 11, 27)


def chain(near_value, *, remote_value=None, mixed=False):
    options, presence = [], {}
    strikes = range(5850, 6151, 10)
    for i, strike in enumerate(strikes):
        for side in "CP":
            iv = (25.0 if i % 2 else .22) if mixed else near_value
            symbol = f"SPXW261123{side}{strike*1000:08d}"
            options.append({"option": symbol, "iv": iv,
                            "open_interest": 200, "gamma": .01})
            presence[symbol] = {"iv": True, "oi": True}
    if remote_value is not None:
        for i in range(120):
            strike = 3000 + i
            symbol = f"SPXW261123C{strike*1000:08d}"
            options.append({"option": symbol, "iv": remote_value,
                            "open_interest": 120, "gamma": 0.000001})
            presence[symbol] = {"iv": True, "oi": True}
    return options, presence


def infer(opts, present, mode="auto", **kwargs):
    return _iv_normalization(
        opts, present, mode, spot=6000,
        target_expiries={"0DTE": EXP, "Weekly": WEEKLY},
        **kwargs,
    )


class IVAutoTests(unittest.TestCase):
    def test_decimal_detected_despite_remote_percent_and_outliers(self):
        opts, present = chain(.22, remote_value=120)
        unit, note = infer(opts, present)
        self.assertEqual(unit, "decimal")
        self.assertIn("vicini allo spot", note)

    def test_percent_detected_despite_remote_decimal(self):
        opts, present = chain(25, remote_value=.01)
        unit, note = infer(opts, present)
        self.assertEqual(unit, "percent")
        self.assertIn("percentuale", note)

    def test_mixed_format_near_money_is_not_guessed(self):
        opts, present = chain(.22, mixed=True)
        unit, note = infer(opts, present)
        self.assertIsNone(unit)
        self.assertIn("mista", note)

    def test_near_money_all_between_1_and_10_remains_ambiguous(self):
        opts, present = chain(4.5)
        self.assertIsNone(infer(opts, present)[0])

    def test_only_missing_near_money_iv_is_not_guessed(self):
        opts, present = chain(.25)
        for item in opts:
            present[item["option"]]["iv"] = False
        unit, message = infer(opts, present)
        self.assertIsNone(unit)
        self.assertIn("non contiene valori IV", message)

    def test_manual_modes_still_available_for_unverifiable_units(self):
        opts, present = chain(4.5)
        self.assertEqual(infer(opts, present, mode="decimal")[0], "decimal")
        self.assertEqual(infer(opts, present, mode="percent")[0], "percent")

    def test_missing_strikes_near_spot_do_not_infer_from_far_only(self):
        opts, present = chain(.2)
        opts = [o for o in opts if o["option"][10] != "C"]  # no effect on expiry
        for o in opts:
            o["open_interest"] = 0
        unit, reason = infer(opts, present)
        self.assertIsNone(unit)
        self.assertIn("solo 0 contratti", reason)


if __name__ == "__main__":
    unittest.main()
