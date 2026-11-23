"""Cross-repository parity: ORIGINAL Edge vs Serafini CSV on IDENTICAL inputs.

This is a separate regression, not a CSV input, Cboe quote or Alpaca
data-quality test. The Edge reference is checked out to a pinned commit
by .github/workflows/edge-engine-parity.yml. No external data/credentials.
"""
from __future__ import annotations

import math
import os
import sys
import unittest
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np

from csv_gex_core import bsm as csv_bsm, config as csv_config, gex as csv_gex
from csv_gex_core.models import Contract as CsvContract

REFERENCE = os.environ.get("EDGE_GEX_REFERENCE_PATH")
if not REFERENCE:
    raise RuntimeError("EDGE_GEX_REFERENCE_PATH required: run this test with pinned Edge source")
reference_root = Path(REFERENCE).resolve()
if not (reference_root / "gexlab/engine/gex.py").is_file():
    raise RuntimeError("Pinned Edge GEX source not found")
sys.path.insert(0, str(reference_root))

from gexlab import config as edge_config  # noqa: E402
from gexlab.engine import bsm as edge_bsm, gex as edge_gex  # noqa: E402
from gexlab.models import Contract as EdgeContract  # noqa: E402


SPOT = 7242.0
AS_OF = datetime(2026, 11, 23, 15, 4, tzinfo=ZoneInfo("America/New_York"))
EXPIRIES = (date(2026, 11, 23), date(2026, 11, 27))
FILE_ROOT = Path(__file__).resolve().parents[1]


def params():
    """Exactly the same OCC identity, OI, IV, spot, T and settlement in both."""
    for expiry in EXPIRIES:
        yymmdd = expiry.strftime("%y%m%d")
        for n in range(161):
            strike = 6800.0 + 5.0 * n
            for side in ("call", "put"):
                index = 2 * n + (side == "put")
                cp = "C" if side == "call" else "P"
                center = 7300 if side == "call" else 7180
                concentration = 950 * math.exp(-.5 * ((strike-center)/62)**2)
                oi = int(90 + concentration + ((n*17+3) % 36))
                if index % 71 == 0:
                    oi = None   # unknown (not falsely 0)
                elif index % 67 == 0:
                    oi = 0      # documented zero
                iv = (.13 if expiry == EXPIRIES[0] else .18)
                iv += .035 * abs(strike-SPOT)/SPOT + .006 * (side=="put")
                if index % 59 == 0:
                    iv = None
                yield {
                    "symbol":f"SPXW{yymmdd}{cp}{round(strike*1000):08d}",
                    "root":"SPXW","expiry":expiry,"settlement":"PM",
                    "strike":strike,"type":side,"multiplier":100,
                    "oi":oi,"oi_date":"2026-11-20" if oi is not None else None,
                    "oi_source":"occ","iv":iv,
                    "iv_source":"same_input_regression",
                }


def two_chains():
    raw=list(params())
    return ([CsvContract(**dict(item)) for item in raw],
            [EdgeContract(**dict(item)) for item in raw])


def numeric_equal(test, actual, expected, field):
    if actual is None or expected is None:
        test.assertIsNone(actual,field)
        test.assertIsNone(expected,field)
        return
    test.assertTrue(math.isclose(float(actual),float(expected),
                                rel_tol=2e-12,abs_tol=1e-8),
                    f"{field}: CSV={actual} Edge={expected}")


class SameInputsOriginalEdgeTests(unittest.TestCase):

    def test_math_source_is_pinned_original_edge_and_not_a_rewrite(self):
        # Vendored mathematical file is allowed to change only module import
        # names and the pinned-source comment. This prevents silent model drift.
        csv_text=(FILE_ROOT/"csv_gex_core/gex.py").read_text()
        edge_text=(reference_root/"gexlab/engine/gex.py").read_text()
        lines=csv_text.splitlines(keepends=True)
        self.assertTrue(lines[0].startswith("# Pinned pure source:"))
        normalized="".join(lines[1:]).replace("csv_gex_core","gexlab")
        normalized=normalized.replace("from gexlab import bsm",
                                      "from gexlab.engine import bsm")
        normalized=normalized.replace("from gexlab.calendar",
                                      "from gexlab.engine.calendar")
        self.assertEqual(normalized,edge_text)

    def test_formula_controls_and_settlements_match(self):
        knobs=(
            "IV_MIN","IV_MAX","COVERAGE_STRIKE_BAND","QUALITY_MIN_PCT",
            "GATE_OI_BAND","GATE_OI_MIN_PCT","GATE_GEX_MIN_PCT",
            "SWEEP_CHUNK","SWEEP_STEP","STOCK_STEP_FRAC","SWEEP_BAND",
            "NEUTRAL_FRAC","WALL_STRIKE_BAND","PROFILE_POINTS",
            "DEFAULT_SETTLE_PM","DEFAULT_SETTLE_AM",
        )
        for key in knobs:
            with self.subTest(key=key):
                self.assertEqual(getattr(csv_config,key),getattr(edge_config,key))
        for T in (1/365, 4/365, 50/365):
            for iv in (.12,.2,.35):
                for strike in (7040,7200,7240,7350):
                    numeric_equal(self,csv_bsm.gamma(SPOT,strike,T,0,iv),
                                  edge_bsm.gamma(SPOT,strike,T,0,iv),
                                  f"BSM(S={SPOT},K={strike},T={T},iv={iv})")

    def test_0dte_weekly_gamma_gex_coverage_walls_flip_and_sweep(self):
        local,ref=two_chains()
        self.assertEqual(len(local),len(ref))
        # Invalidate exactly the same contracts in both engines.
        local=csv_gex.finalize(local,SPOT,AS_OF,None)
        ref=edge_gex.finalize(ref,SPOT,AS_OF,None)
        self.assertEqual(len(local),644)
        for a,b in zip(local,ref):
            self.assertEqual((a.symbol,a.strike,a.expiry,a.oi,a.iv),
                             (b.symbol,b.strike,b.expiry,b.oi,b.iv))
            self.assertEqual((a.valid,a.invalid_reason),(b.valid,b.invalid_reason))
            numeric_equal(self,a.T,b.T,"time_to_settlement")
            numeric_equal(self,a.gamma,b.gamma,"gamma")
            numeric_equal(self,a.gex,b.gex,"signed_gex")

        for label,expiry in (("0DTE",EXPIRIES[0]),("Weekly",EXPIRIES[1]),
                             ("Both expiries",None)):
            with self.subTest(case=label):
                left=[x for x in local if expiry is None or x.expiry==expiry]
                right=[x for x in ref if expiry is None or x.expiry==expiry]
                lc=csv_gex.coverage(left,SPOT)
                rc=edge_gex.coverage(right,SPOT)
                self.assertEqual((lc.eligible,lc.valid),(rc.eligible,rc.valid))
                numeric_equal(self,lc.ratio,rc.ratio,"contract_coverage")
                lg=csv_gex.gex_cov(left,SPOT)
                rg=edge_gex.gex_cov(right,SPOT)
                numeric_equal(self,lg.ratio,rg.ratio,"gex_coverage")
                self.assertEqual(lg.left_out,rg.left_out)
                self.assertEqual(csv_gex.gex_gate_ok(lg),
                                 edge_gex.gex_gate_ok(rg))
                lf=csv_gex.oi_freshness(left,SPOT,"2026-11-20")
                rf=edge_gex.oi_freshness(right,SPOT,"2026-11-20")
                numeric_equal(self,lf.stale_frac,rf.stale_frac,"oi_freshness")
                self.assertEqual(lf.dates,rf.dates)
                llevels,lgrid,lgex=csv_gex.compute_levels("SPX",left,SPOT)
                rlevels,rgrid,rgex=edge_gex.compute_levels("SPX",right,SPOT)
                self.assertEqual((llevels.call_wall,llevels.put_wall),
                                 (rlevels.call_wall,rlevels.put_wall))
                self.assertEqual(llevels.regime,rlevels.regime)
                self.assertEqual(len(llevels.zero_gamma),len(rlevels.zero_gamma))
                numeric_equal(self,llevels.nearest_zero_gamma,
                              rlevels.nearest_zero_gamma,"gamma_flip")
                numeric_equal(self,llevels.net_gex,rlevels.net_gex,"net_gex")
                numeric_equal(self,llevels.gross_gex,rlevels.gross_gex,"gross_gex")
                np.testing.assert_allclose(lgrid,rgrid,rtol=0,atol=0)
                np.testing.assert_allclose(lgex,rgex,rtol=1e-12,atol=1e-6)
                lcurve=csv_gex.profile_curve(left,SPOT,points=201)
                rcurve=edge_gex.profile_curve(right,SPOT,points=201)
                np.testing.assert_allclose(
                    [row["net_gex"] for row in lcurve],
                    [row["net_gex"] for row in rcurve],
                    rtol=1e-12,atol=1e-6)
                print("PARITY_OK",label,"contracts",len(left),
                      "valid",sum(c.valid for c in left),
                      "call_wall",llevels.call_wall,
                      "put_wall",llevels.put_wall,
                      "gamma_flip",llevels.nearest_zero_gamma,
                      "net_gex",round(llevels.net_gex,3),
                      "coverage_gex",lg.pct)
                # This regression validates math, not market-data truth.
                # No Alpaca/Cboe/OCC live connection and no file output.


if __name__ == "__main__":
    unittest.main()
