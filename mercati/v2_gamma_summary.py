"""Presentation-only Serafini NET/CALL/PUT summaries for shown option profiles.

No Gamma calculations or original Cboe records are modified. The metrics
aggregate exactly the rows supplied by the rendered profile collection.
"""
import math
import streamlit as st


def format_gamma_it(value, *, signed=False):
    value = float(value)
    if not math.isfinite(value):
        raise ValueError("Valore Gamma non finito")
    us = f"{value:+,.2f}" if signed else f"{value:,.2f}"
    return us.replace(",", "_").replace(".", ",").replace("_", ".")


def gamma_totals(profiles, *, net_key, call_key, put_key):
    rows = [row for p in profiles for row in p["rows"]]
    total = {
        "net": sum(float(row[net_key]) for row in rows),
        "call": sum(float(row[call_key]) for row in rows),
        "put": sum(float(row[put_key]) for row in rows),
    }
    if not all(math.isfinite(x) for x in total.values()):
        raise ValueError("Gamma non finito nelle scadenze visualizzate")
    # Keep the actual source net untouched; do not silently replace it.
    return total


def render_gamma_summary(profiles, *, net_key, call_key, put_key):
    totals = gamma_totals(profiles, net_key=net_key,
                          call_key=call_key, put_key=put_key)
    net_col, call_col, put_col = st.columns(3)
    for col, label, value in (
        (net_col, "NET GAMMA · Call − Put", totals["net"]),
        (call_col, "GAMMA CALL (+)", totals["call"]),
        (put_col, "GAMMA PUT (−)", -totals["put"]),
    ):
        color = "#f05252" if value < 0 else "#f1f5f9"
        formatted = format_gamma_it(value, signed=True).replace("-", "−")
        with col:
            st.markdown(
                '<div style="font-size:0.88rem;color:#d1d5db;margin-bottom:0.35rem">' + label + '</div>'
                f'<div style="font-size:1.85rem;line-height:1.25;font-weight:400;color:{color};'
                f'font-variant-numeric:tabular-nums">{formatted}</div>',
                unsafe_allow_html=True,
            )
    st.caption("Somma dei soli profili mostrati (scadenze e strike selezionati). "
               "Gamma originali CBOE, non monetari; nessuna esposizione dealer osservata.")
    return totals
