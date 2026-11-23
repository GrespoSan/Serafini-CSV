"""Estensione SPX: nucleo Serafini invariato, copertura estesa e budget Pine."""
import unittest
from datetime import date

from net_gamma import profile, visual_profile, gamma_component_totals
from pine_export import make_pine

DAY = date(2026, 11, 23)
WEEK = date(2026, 11, 27)


def snapshot():
    rows = []
    for expiry in (DAY, WEEK):
        yymmdd = expiry.strftime("%y%m%d")
        for strike in range(5400, 6601):
            for side in ("C", "P"):
                # Valori Cboe sintetici ma sempre positivi; univoci e verificabili.
                g = 0.02 + ((strike - 5400) % 17) * 0.0001
                rows.append({
                    "option": f"SPXW{yymmdd}{side}{strike * 1000:08d}",
                    "gamma": g, "volume": 10, "open_interest": 100 + strike % 23,
                })
    return {"symbol": "SPX", "timestamp": "2026-11-23 07:22:00",
            "data": {"options": rows, "current_price": 6000,
                     "prev_day_close": 6000}}


class ExtendedNetGammaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.snap = snapshot()
        cls.core_day = profile(cls.snap, DAY, 6000)
        cls.core_week = profile(cls.snap, WEEK, 6000)

    def test_original_25plus25_untouched_even_if_visual_has_200(self):
        v = visual_profile(self.snap, self.core_day, DAY, 6000, spot=6000,
                           buffer_pct=.05)
        self.assertEqual(len(self.core_day["rows"]), 50)
        self.assertEqual(len(v["rows"]), 200)
        self.assertEqual(v["core_strikes"], 50)
        self.assertEqual(v["extra_strikes"], 150)
        self.assertTrue(v["coverage_complete"])
        self.assertLessEqual(v["actual_low"], 5701)
        self.assertGreaterEqual(v["actual_high"], 6299)
        original = {r["strike_spx"]: r["net_gamma"] for r in self.core_day["rows"]}
        extended = {r["strike_spx"]: r["net_gamma"] for r in v["rows"]}
        self.assertEqual(
            {k: extended[k] for k in original}, original)
        self.assertEqual(len(extended), len(v["rows"]))
        # Lo strike esattamente a 6000 non fa parte del nucleo originale
        # Serafini (25 strettamente sotto + 25 strettamente sopra) e non
        # viene inserito artificialmente dall'estensione grafica.
        self.assertEqual(v["source_strikes_in_range"], 600)
        self.assertEqual(v["sampled_strikes"], 400)

    def test_current_snapshot_spot_and_previous_ref_change_target(self):
        v = visual_profile(self.snap, self.core_day, DAY, 6000, spot=6100,
                           buffer_pct=.05)
        self.assertAlmostEqual(v["requested_low"], 5700)
        self.assertAlmostEqual(v["requested_high"], 6400)
        self.assertTrue(v["coverage_complete"])

    def test_known_previous_rth_widens_target_but_never_fakes_strikes(self):
        v = visual_profile(
            self.snap, self.core_day, DAY, 6000, spot=6000,
            known_low=5450, known_high=6450, buffer_pct=.05,
        )
        self.assertAlmostEqual(v["requested_low"], 5150)
        self.assertAlmostEqual(v["requested_high"], 6750)
        self.assertFalse(v["coverage_complete"])
        self.assertEqual(min(r["strike_spx"] for r in v["rows"]), 5400)
        self.assertEqual(max(r["strike_spx"] for r in v["rows"]), 6600)
        self.assertLessEqual(len(v["rows"]), 200)

    def test_quiet_day_core_sufficient_and_no_other_options_read(self):
        # Senza lista opzioni: se 25+25 bastano, nessun altro contratto
        # viene letto o ricalcolato.
        visual = visual_profile(
            {}, self.core_day, DAY, 6000, spot=6003,
            known_low=5995, known_high=6007,
        )
        self.assertEqual(visual["decision"], "50_sufficienti")
        self.assertTrue(visual["coverage_complete"])
        self.assertEqual(visual["band_mode"], "adattivo")
        self.assertEqual(visual["extra_strikes"], 0)
        self.assertEqual(visual["rows"], self.core_day["rows"])
        self.assertEqual(visual["source_strikes_in_range"], 50)
        self.assertEqual(visual["sampled_strikes"], 0)
        self.assertGreaterEqual(visual["requested_low"], 5975)
        self.assertLessEqual(visual["requested_high"], 6025)

    def test_only_upper_side_extended_when_price_exceeds_core(self):
        visual = visual_profile(
            self.snap, self.core_day, DAY, 6000, spot=6030,
        )
        self.assertEqual(visual["decision"], "estesa_sopra")
        self.assertFalse(visual["need_low"])
        self.assertTrue(visual["need_high"])
        self.assertEqual(visual["actual_low"], 5975)
        self.assertEqual(visual["actual_high"], 6045)
        self.assertEqual(visual["extra_strikes"], 20)
        self.assertEqual(len(visual["rows"]), 70)
        self.assertTrue(visual["coverage_complete"])

    def test_only_lower_side_extended_when_prior_low_exceeds_core(self):
        visual = visual_profile(
            self.snap, self.core_day, DAY, 6000,
            spot=6002, known_low=5960, known_high=6006,
        )
        self.assertEqual(visual["decision"], "estesa_sotto")
        self.assertTrue(visual["need_low"])
        self.assertFalse(visual["need_high"])
        self.assertLess(visual["actual_low"], 5975)
        self.assertEqual(visual["actual_high"], 6025)
        self.assertTrue(visual["coverage_complete"])

    def test_automatic_extension_preserves_pine_default_and_core_only_geometry(self):
        quiet = visual_profile(
            self.snap, self.core_day, DAY, 6000,
            spot=6000, known_low=5990, known_high=6010,
        )
        quiet_week = visual_profile(
            self.snap, self.core_week, WEEK, 6000,
            spot=6000, known_low=5990, known_high=6010,
        )
        self.assertEqual(quiet["extra_strikes"], 0)
        self.assertEqual(quiet_week["extra_strikes"], 0)
        p0 = make_pine(
            self.core_day, self.core_week, 40.0,
            DAY.isoformat(), "2026-11-23 07:22:00",
            current_only=True,
        )
        p1 = make_pine(
            dict(self.core_day, display_rows=quiet["rows"]),
            dict(self.core_week, display_rows=quiet_week["rows"]),
            40.0, DAY.isoformat(), "2026-11-23 07:22:00",
            current_only=True,
        )
        self.assertEqual(p0, p1)
        self.assertIn(
            'showExtension = input.bool(true, "Estensione automatica NET GAMMA")',
            p1,
        )

    def test_visual_extension_does_not_recalculate_gamma(self):
        v = visual_profile(self.snap, self.core_day, DAY, 6000, spot=6000,
                           buffer_pct=.05)
        for row in v["rows"]:
            self.assertAlmostEqual(
                row["net_gamma"],
                row["call_gamma_component"] - row["put_gamma_component"],
            )

    def test_canonical_totals_do_not_change_with_graphical_extension(self):
        core = gamma_component_totals(
            [self.core_day, self.core_week], require_core=True
        )
        self.assertEqual(core["strikes"], 100)
        self.assertEqual(core["profiles"], 2)
        self.assertAlmostEqual(core["net"], core["call"] - core["put"])
        for cap, margin in ((50, .025), (140, .025), (200, .05)):
            with self.subTest(strikes=cap, margin=margin):
                v0 = visual_profile(
                    self.snap, self.core_day, DAY, 6000,
                    spot=6000, buffer_pct=margin, max_strikes=cap
                )
                vw = visual_profile(
                    self.snap, self.core_week, WEEK, 6000,
                    spot=6000, buffer_pct=margin, max_strikes=cap
                )
                # Il riepilogo canonico deriva soltanto da computed_profiles.
                actual = gamma_component_totals(
                    [self.core_day, self.core_week], require_core=True
                )
                self.assertEqual(actual, core)
                # La somma delle righe visualizzate cambia, ma è audit separato.
                vis = gamma_component_totals([v0, vw])
                self.assertEqual(vis["strikes"], 2 * cap)
                self.assertAlmostEqual(vis["net"], vis["call"] - vis["put"])

    def test_reject_noncanonical_rows_as_original_totals(self):
        v0 = visual_profile(
            self.snap, self.core_day, DAY, 6000,
            spot=6000, max_strikes=200, buffer_pct=.05
        )
        with self.assertRaisesRegex(ValueError, "25\\+25"):
            gamma_component_totals([v0], require_core=True)

    def test_app_summary_uses_core_without_audit_panel(self):
        from pathlib import Path
        source = (Path(__file__).resolve().parents[1] /
                  "gamma_section.py").read_text(encoding="utf-8")
        self.assertIn("computed_profiles.values(), require_core=True", source)
        self.assertIn("max_strikes=200,  # margine adattivo", source)
        self.assertNotIn("buffer_pct=.05, max_strikes=200", source)
        self.assertIn("'Estensione intelligente NET GAMMA — solo grafici'", source)
        self.assertNotIn("Audit: differenza tra NET GAMMA originale e profili estesi", source)
        self.assertNotIn("graphical_summary = gamma_component_totals(", source)
        self.assertNotIn("shown_rows = [row for p in shown_profiles", source)

    def test_pine_handles_200_per_profile(self):
        v0 = visual_profile(self.snap, self.core_day, DAY, 6000, spot=6000,
                            buffer_pct=.05)
        vw = visual_profile(self.snap, self.core_week, WEEK, 6000, spot=6000,
                            buffer_pct=.05)
        a = dict(self.core_day, display_rows=v0["rows"])
        b = dict(self.core_week, display_rows=vw["rows"])
        code = make_pine(a, b, 40.0, DAY.isoformat(),
                         "2026-11-23 07:22:00", current_only=True)
        self.assertIn("var array<float> odteLevels", code)
        self.assertIn("var array<float> weeklyLevels", code)
        self.assertIn("Mostra 0DTE", code)
        self.assertIn("MAX 200 per profilo", code)
        # Nessun secondo gruppo GEX Edge quando la fonte è esclusivamente CSV.
        self.assertNotIn("GEX Edge 0DTE", code)
        self.assertNotIn("showGexLevels = input.bool", code)


if __name__ == "__main__":
    unittest.main()
