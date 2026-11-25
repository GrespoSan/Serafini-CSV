"""Ultime 5 RTH M15 verificate per estensione grafica, senza look-ahead."""
from datetime import date
from pathlib import Path
import unittest

import pandas as pd

from serafini_sigma import compute_recent_rth_range
from net_gamma import visual_profile, profile

ROOT = Path(__file__).resolve().parents[1]
CAPTURE_DAY = date(2026, 11, 25)


def cash_history(*, corrupted=None, add_future=False):
    # Le ultime cinque sedute cash precedenti il CSV 25/11 sono
    # 18, 19, 20, 23 e 24 novembre. Il minimo estremo e' il 23.
    dates = [date(2026, 11, n) for n in (18, 19, 20, 23, 24)]
    if add_future:
        dates.append(CAPTURE_DAY)
    frames = []
    for d in dates:
        idx = pd.date_range(
            start=pd.Timestamp(d).tz_localize("America/Chicago")
                  + pd.Timedelta(hours=8, minutes=30),
            periods=27, freq="15min",
        )
        low = 7140.0
        high = 7275.0
        if d == date(2026, 11, 23):
            low, high = 6920.0, 7300.0
        if d == date(2026, 11, 20):
            high = 7380.0
        if d == CAPTURE_DAY:
            low, high = 6500.0, 8000.0  # FUTURO: non utilizzabile
        frame = pd.DataFrame({
            "High": [high] * 27,
            "Low": [low] * 27,
            "Close": [(low + high) / 2.0] * 27,
        }, index=idx)
        if corrupted == d:
            frame = frame.drop(frame.index[6])
        frames.append(frame)
    return pd.concat(frames).sort_index()


class RecentRTHTests(unittest.TestCase):
    def test_five_complete_sessions_capture_prior_extreme(self):
        result = compute_recent_rth_range(cash_history(), CAPTURE_DAY)
        self.assertEqual(result["recent_rth_sessions"], 5)
        self.assertEqual(result["recent_rth_start_chicago"], "2026-11-18")
        self.assertEqual(result["recent_rth_end_chicago"], "2026-11-24")
        self.assertEqual(result["recent_rth_low_es"], 6920.0)
        self.assertEqual(result["recent_rth_high_es"], 7380.0)

    def test_future_bars_of_capture_day_not_used(self):
        data = compute_recent_rth_range(
            cash_history(add_future=True), CAPTURE_DAY,
        )
        self.assertEqual(data["recent_rth_low_es"], 6920.0)
        self.assertEqual(data["recent_rth_high_es"], 7380.0)
        self.assertEqual(data["recent_rth_end_chicago"], "2026-11-24")

    def test_missing_any_rth_bar_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "27 M15 complete"):
            compute_recent_rth_range(
                cash_history(corrupted=date(2026, 11, 23)), CAPTURE_DAY,
            )

    def test_more_than_five_sessions_only_five_latest(self):
        before = pd.date_range(
            start=pd.Timestamp(date(2026, 11, 17)).tz_localize("America/Chicago")
                  + pd.Timedelta(hours=8, minutes=30),
            periods=27, freq="15min",
        )
        extra = pd.DataFrame({
            "High": [8800.0] * 27,
            "Low": [5000.0] * 27,
            "Close": [7100.0] * 27,
        }, index=before)
        data = compute_recent_rth_range(
            pd.concat([cash_history(), extra]), CAPTURE_DAY,
        )
        self.assertEqual(data["recent_rth_low_es"], 6920.0)
        self.assertEqual(data["recent_rth_high_es"], 7380.0)

    def test_fewer_than_three_complete_sessions_rejected(self):
        data = cash_history().loc[
            lambda f: f.index.date >= date(2026, 11, 23)
        ]
        with self.assertRaisesRegex(ValueError, "Meno di tre"):
            compute_recent_rth_range(data, CAPTURE_DAY)

    def test_extreme_low_results_in_real_strikes_below_core(self):
        from tests.test_net_gamma_dynamic_extension import (
            snapshot, DAY,
        )
        snap = snapshot()
        core = profile(snap, DAY, 6000.0)
        # Trasferimento puramente grafico del range RTH nel riferimento
        # SPX con un offset noto; nucleo 25+25 invariato.
        data = compute_recent_rth_range(cash_history(), CAPTURE_DAY)
        visual = visual_profile(
            snap, core, DAY, 6000, spot=6005,
            known_low=data["recent_rth_low_es"] - 940,
            known_high=data["recent_rth_high_es"] - 940,
        )
        self.assertEqual(visual["decision"], "estesa_entrambi")
        self.assertTrue(visual["need_low"])
        self.assertTrue(visual["need_high"])
        self.assertLess(visual["actual_low"], 5975)
        self.assertGreater(visual["actual_high"], 6025)
        self.assertEqual(len(core["rows"]), 50)

    def test_app_uses_five_rth_when_available_safety_when_not(self):
        code = (ROOT / "gamma_section.py").read_text(encoding="utf-8")
        self.assertIn("recent_rth_sessions", code)
        self.assertIn("fallback_buffer = .05", code)
        self.assertIn("fallback_buffer = None", code)
        self.assertIn("max_strikes=200, buffer_pct=fallback_buffer", code)
        self.assertIn("date.fromisoformat(str(last_session)) < day", code)
        self.assertIn("25+25", code)


if __name__ == "__main__":
    unittest.main()
