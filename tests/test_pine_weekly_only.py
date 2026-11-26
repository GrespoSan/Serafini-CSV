"""Pine solo Weekly per Thanksgiving/0DTE assente, senza livelli sintetici."""
from datetime import date
from pathlib import Path
import unittest

from net_gamma import profile, visual_profile
from pine_export import make_pine, make_pine_weekly_only


ROOT = Path(__file__).resolve().parents[1]
WEEK = date(2026, 11, 27)
ODTE = date(2026, 11, 26)
REF = 7200.0
BASIS = 16.0
STAMP = "2026-11-26 01:05:00"


def fake_snapshot():
    """Fixture sintetico, NON una misura reale del CSV dell'utente."""
    contracts = []
    for expiry in (ODTE, WEEK):
        for strike in range(6900, 7501, 5):
            for side in ("C", "P"):
                contracts.append({
                    "option": f"SPXW{expiry:%y%m%d}{side}{strike * 1000:08d}",
                    "open_interest": 300,
                    "volume": 12,
                    "gamma": 0.035 + (strike - 6900) / 1e6,
                })
    return {"data": {"options": contracts}}


def weekly():
    return profile(fake_snapshot(), WEEK, REF)


def odte():
    return profile(fake_snapshot(), ODTE, REF)


class PineWeeklyOnlyTests(unittest.TestCase):
    def test_weekly_only_has_original_50_no_0dte_arrays_or_controls(self):
        wk = weekly()
        self.assertEqual(len(wk["rows"]), 50)
        text = make_pine_weekly_only(
            wk, BASIS, ODTE.isoformat(), STAMP,
            acquisition_label="Fotografia CSV Cboe", current_only=True,
        )
        self.assertTrue(text.startswith("//@version=6\n"))
        self.assertIn("NET GAMMA WEEKLY ONLY", text)
        self.assertIn("Weekly 02:05 Roma", text)
        self.assertIn("scadenza Weekly: 2026-11-27", text)
        self.assertIn("// EXPORT PROFILE: WEEKLY_ONLY", text)
        self.assertIn("var array<float> weeklyLevels", text)
        self.assertIn("var array<float> weeklyValues", text)
        self.assertIn("Mostra Weekly corrente", text)
        self.assertIn("Estensione automatica NET GAMMA", text)
        self.assertIn("renderWeekly(weeklyLevels, weeklyValues", text)
        self.assertNotIn("var array<float> odte", text)
        self.assertNotIn("showCurrentOdte", text)
        self.assertNotIn("showTop3Odte", text)
        self.assertNotIn("topCallFull", text)
        self.assertNotIn("renderProfile(odteLevels", text)
        self.assertIn("NESSUN livello 0DTE", text)

    def test_extension_reuses_real_strikes_and_preserves_all_50(self):
        snapshot = fake_snapshot()
        core = profile(snapshot, WEEK, REF)
        extended = visual_profile(
            snapshot, core, WEEK, REF, spot=7197,
            buffer_pct=.05, max_strikes=200,
        )
        self.assertEqual(len(core["rows"]), 50)
        self.assertGreater(len(extended["rows"]), 50)
        wk = dict(core, display_rows=extended["rows"])
        result = make_pine_weekly_only(
            wk, BASIS, ODTE.isoformat(), STAMP,
        )
        self.assertIn("weeklyCoreValues", result)
        self.assertIn("weeklyLevels", result)
        self.assertIn("showExtension ? weeklyValues : weeklyCoreValues", result)
        # The source 25+25 must not be adjusted or normalized.
        self.assertEqual(wk["rows"], core["rows"])
        self.assertLessEqual(len(extended["rows"]), 200)
        self.assertIn("Data fotografia: 2026-11-26", result)

    def test_export_does_not_change_normal_complete_0dte_weekly(self):
        output = make_pine(
            odte(), weekly(), BASIS, ODTE.isoformat(), STAMP,
            current_only=True,
        )
        self.assertIn("var array<float> odteLevels", output)
        self.assertIn("var array<float> weeklyLevels", output)
        self.assertIn("Mostra 0DTE corrente", output)
        self.assertIn("Mostra Weekly corrente", output)
        self.assertNotIn("// EXPORT PROFILE: WEEKLY_ONLY", output)

    def test_reject_absent_or_short_weekly_and_forged_extension(self):
        valid = weekly()
        with self.assertRaisesRegex(ValueError, "25\\+25"):
            make_pine_weekly_only(
                dict(valid, rows=[]), BASIS, ODTE.isoformat(), STAMP,
            )
        with self.assertRaisesRegex(ValueError, "25\\+25"):
            make_pine_weekly_only(
                dict(valid, rows=valid["rows"][:25]), BASIS,
                ODTE.isoformat(), STAMP,
            )
        bad_extension = valid["rows"][1:] + [
            dict(valid["rows"][-1], strike_spx=9000),
        ]
        with self.assertRaisesRegex(ValueError, "invariati"):
            make_pine_weekly_only(
                dict(valid, display_rows=bad_extension), BASIS,
                ODTE.isoformat(), STAMP,
            )

    def test_unverified_basis_or_stamp_rejected(self):
        for offset in (float("nan"), float("inf")):
            with self.assertRaisesRegex(ValueError, "Differenziale"):
                make_pine_weekly_only(
                    weekly(), offset, ODTE.isoformat(), STAMP,
                )
        with self.assertRaisesRegex(ValueError, "Timestamp"):
            make_pine_weekly_only(
                weekly(), BASIS, ODTE.isoformat(), "not-a-time",
            )

    def test_ui_requires_weekly_and_does_not_fabricate_odte(self):
        src = (ROOT / "gamma_section.py").read_text(encoding="utf-8")
        self.assertIn("valid_weekly = bool(", src)
        self.assertIn("valid_odte = bool(", src)
        self.assertIn("make_pine_weekly_only(", src)
        self.assertIn("Pine disponibile — SOLO WEEKLY", src)
        self.assertIn("SPX_NET_GAMMA_WEEKLY_ONLY_", src)
        self.assertIn("script = make_pine(", src)
        self.assertIn("if offset is not None and math.isfinite(offset) and valid_weekly:", src)
        self.assertIn("Pine NET GAMMA non disponibile:", src)

    def test_weekly_only_csv_gex_restricts_overlay_to_weekly(self):
        src = (ROOT / "mercati/pine_ui.py").read_text(encoding="utf-8")
        self.assertIn('if "// EXPORT PROFILE: WEEKLY_ONLY" in code:', src)
        self.assertIn('valid = {k: v for k, v in valid.items() if k == "Weekly"}', src)
        self.assertIn("resta il solo NET GAMMA Weekly", src)


if __name__ == "__main__":
    unittest.main()
