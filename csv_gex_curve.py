"""Pure global extrema for the already calculated 201-point GEX curve."""
from __future__ import annotations

import math

from csv_gex_price_display import gex_display_price


def curve_extrema(report, *, symbol, es_spx_basis=None):
    """Global extrema within ±10% theoretical scenario; NOT strike extrema."""
    curve=report.get("curve") or []
    values=[]
    for row in curve:
        try:
            price=gex_display_price(row["spot"],symbol,es_spx_basis)
            gex=float(row["net_gex"])
            if price is None or not math.isfinite(gex):
                return None
            values.append((price,gex))
        except (ValueError,TypeError,KeyError,OverflowError):
            return None
    if len(values)<2:
        return None
    center=values[len(values)//2][0]
    high=max(values,key=lambda p:(p[1],-abs(p[0]-center)))
    low=min(values,key=lambda p:(p[1],abs(p[0]-center)))
    return {"maximum":{"price":high[0],"gex":high[1]},
            "minimum":{"price":low[0],"gex":low[1]}}
