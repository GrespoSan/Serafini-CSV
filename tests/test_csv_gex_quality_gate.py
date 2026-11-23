"""Qualità Edge: gate GEX non arrotondato, copertura contratti diagnostica.

Reproduce il caso mostrato: 360 validi / 387 = 93.0% mentre il GEX
stimato nella banda +/-5% è coperto quasi interamente. Non allenta la
soglia 98% di GEX e non cambia l'assenza di data OI certificata.
"""
import math
import unittest
from datetime import date

from csv_gex_core.bsm import gamma
from csv_gex_core.models import Contract
from csv_gex_core import gex
from csv_gex_engine import _report

EXPIRY = date(2026, 11, 27)
SPOT = 6000.0
T = 1.0 / 365.0


def make_contract(strike, option_type, oi=100, iv=.20, *, valid=True, idx=0):
    cp = "C" if option_type == "call" else "P"
    symbol = f"SPXW261127{cp}{round(strike * 1000):08d}"
    c = Contract(
        symbol=symbol, root="SPXW", expiry=EXPIRY, settlement="PM",
        strike=float(strike), type=option_type, multiplier=100,
        oi=int(oi), iv=iv if valid else None,
    )
    c.T = T
    c.valid = valid
    if valid:
        c.gamma = gamma(SPOT, c.strike, T, 0.0, iv)
        c.gex = gex.contract_gex(
            c.gamma, c.oi, c.multiplier, SPOT, gex.sign_of(option_type)
        )
    else:
        c.invalid_reason = "no_iv"
    return c


def chain(high_impact_invalid=False):
    contracts = [
        make_contract(
            5800.0 + 400.0 * i / 359.0,
            "call" if i % 2 == 0 else "put",
        )
        for i in range(360)
    ]
    for i in range(27):
        # Tutti gli invalidi hanno OI > 0 e contano nel denominatore;
        # quando sono vicino a 5% OTM hanno sensibilità modesta.
        k = 5990.0 + i if high_impact_invalid else 6271.0 + i
        oi = 1000 if high_impact_invalid else 100
        contracts.append(make_contract(k, "call", oi=oi, valid=False))
    return contracts


class EdgeQualityGateTests(unittest.TestCase):
    def test_360_of_387_with_valid_gex_coverage_is_diagnostic_not_blocked(self):
        contracts = chain()
        cov = gex.coverage(contracts, SPOT)
        gcov = gex.gex_cov(contracts, SPOT)
        self.assertEqual((cov.valid, cov.eligible), (360, 387))
        self.assertLess(cov.ratio, .95)
        self.assertIsNotNone(gcov.ratio)
        self.assertGreaterEqual(gcov.ratio, .98)
        self.assertTrue(gex.gex_gate_ok(gcov))
        result = _report(
            EXPIRY, "Weekly", contracts, SPOT, "SPX",
            "Solo diagnostico: data OI e quote non certificate.",
        )
        self.assertEqual(result["status"], "DIAGNOSTICO")
        self.assertFalse(result["quality_certified"])
        self.assertTrue(math.isfinite(result["net_gex"]))
        self.assertEqual(len(result["curve"]), 201)
        self.assertIn("non bloccante", result["reason"])

    def test_low_gex_coverage_is_still_blocked(self):
        contracts = chain(high_impact_invalid=True)
        gcov = gex.gex_cov(contracts, SPOT)
        self.assertIsNotNone(gcov.ratio)
        self.assertLess(gcov.ratio, .98)
        result = _report(
            EXPIRY, "Weekly", contracts, SPOT, "SPX", "test",
        )
        self.assertEqual(result["status"], "INSUFFICIENTE")
        self.assertIsNone(result["call_wall"])
        self.assertIsNone(result["put_wall"])
        self.assertIsNone(result["flip"])
        self.assertIsNone(result["net_gex"])
        self.assertEqual(result["curve"], [])


if __name__ == "__main__":
    unittest.main()
