"""Riferimento ES Yahoo indicativo per gli istogrammi SPX NET GAMMA.

Pure UI overlay: non modifica righe Cboe, NET GAMMA, scala orizzontale,
GEX, differenziale ES-SPX o l'esportazione Pine.
"""
from __future__ import annotations

import math


def add_es_quote_to_net_gamma(fig, strike_prices, quote, *, has_es_axis: bool):
    """Aggiunge linea ES e cartellino solo con fonte/ora/prezzo verificati.

    Se il prezzo è fuori dagli strike presenti, allarga SOLO l'asse prezzi
    per renderlo visibile; le barre originali restano alle stesse ordinate.
    Restituisce stato auditabile per didascalia Streamlit.
    """
    if not has_es_axis:
        return {"shown": False, "reason": "Scala SPX: differenziale ES-SPX non disponibile"}
    if not isinstance(quote, dict) or quote.get("price") is None:
        return {"shown": False, "reason": "Prezzo ES Yahoo non disponibile (N/D)"}
    try:
        price = float(quote["price"])
        age = float(quote["age_minutes"])
        prices = [float(p) for p in strike_prices]
    except (ValueError, TypeError, OverflowError, KeyError):
        return {"shown": False, "reason": "Quotazione ES non verificabile"}
    if (quote.get("source") != "YAHOO_FINANCE_CHART"
            or not quote.get("observed_rome")
            or not quote.get("symbol")
            or not prices or not all(math.isfinite(v) and v > 0 for v in prices)
            or not (math.isfinite(price) and price > 0
                    and math.isfinite(age) and 0 <= age <= 90)):
        return {"shown": False, "reason": "Quotazione ES assente o troppo vecchia"}
    outside = not min(prices) <= price <= max(prices)
    fig.add_hline(
        y=price, line_color="#fb923c", line_dash="dash", line_width=2.1,
    )
    fig.add_annotation(
        x=0.995, xref="paper", y=price, yref="y",
        text=f"ES Yahoo {price:,.2f}", showarrow=False,
        xanchor="right", yanchor="bottom",
        font=dict(color="#fb923c", size=12),
        bgcolor="rgba(16,17,22,0.91)", bordercolor="#fb923c",
        borderwidth=1, borderpad=3,
    )
    if outside:
        # yaxis è solo una scala di PREZZO; nessun intervento sulle
        # componenti NET GAMMA, loro xaxis o sul contenuto del Pine.
        low = min(min(prices), price)
        high = max(max(prices), price)
        pad = max(2.0, (high - low) * .025)
        fig.update_yaxes(range=[low - pad, high + pad])

    return {
        "shown": True,
        "outside_strikes": outside,
        "price": price,
        "symbol": str(quote["symbol"]),
        "observed_rome": str(quote["observed_rome"]),
        "age_minutes": age,
        "contract_kind": quote.get("contract_kind"),
    }
