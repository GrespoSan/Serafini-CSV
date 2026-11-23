"""Pannello GEX diagnostico indipendente, fonte solo CSV caricato."""
from __future__ import annotations
import hashlib

import plotly.graph_objects as go
import streamlit as st
from csv_gex_engine import analyze_csv_gex, MODEL_LABEL


@st.cache_data(show_spinner=False, max_entries=6, ttl=3600)
def _cached_gex(blob, symbol, units):
    return analyze_csv_gex(blob, symbol, units)


def _number(value):
    return f"{value:,.2f}" if value is not None else "N/D"


def _gex_metric(column, label, value, *, negative=False, key=""):
    """Colora solo il VALORE negativo; label e stile Streamlit restano intatti."""
    if negative:
        with column:
            with st.container(key=f"csv_gex_negative_{key}"):
                st.metric(label, value)
    else:
        column.metric(label, value)


def _curve_chart(report, spot):
    grid = report["curve"]
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=[row["spot"] for row in grid],
        y=[row["net_gex"] / 1e9 for row in grid],
        mode="lines", line=dict(color="#43d6ee", width=2.5),
        name="GEX scenario",
        hovertemplate="Spot teorico %{x:,.2f}<br>NET GEX %{y:+.3f} mld<extra></extra>",
    ))
    fig.add_hline(y=0, line_color="#717984", line_width=1)
    fig.add_vline(x=spot, line_dash="dot", line_color="#f4f5f6",
                  annotation_text="Spot del CSV")
    for value, color, label in (
        (report["call_wall"], "#22c55e", "Call Wall"),
        (report["put_wall"], "#ef4444", "Put Wall"),
        (report["flip"], "#facc15", "Gamma Flip"),
    ):
        if value is not None:
            fig.add_vline(x=float(value), line_dash="dash", line_color=color,
                          annotation_text=label, annotation_position="top")
    fig.update_layout(
        template="plotly_dark", height=450,
        margin=dict(l=18, r=25, t=35, b=30),
        xaxis_title="Scenario teorico prezzo sottostante",
        yaxis_title="NET GEX (mld USD / movimento 1%)",
        showlegend=False,
    )
    return fig


def _strikes_chart(report):
    rows = report["rows"]
    fig = go.Figure()
    for field, name, color in (
        ("call_gex", "Call GEX (+)", "#22c55e"),
        ("put_gex", "Put GEX (−)", "#ef4444"),
    ):
        fig.add_trace(go.Bar(
            y=[r["strike"] for r in rows],
            x=[r[field] / 1e9 for r in rows],
            orientation="h", marker_color=color, name=name,
        ))
    fig.update_layout(
        template="plotly_dark", height=490, barmode="relative",
        margin=dict(l=18, r=25, t=28, b=30),
        xaxis_title="GEX stimato (mld USD / movimento 1%)",
        yaxis_title="Strike originale CSV",
        legend=dict(orientation="h"),
    )
    return fig


def render(payload: bytes | None, symbol: str | None) -> None:
    st.caption(
        "**Modulo autonomo · fonte CSV Cboe.** "
        "Matematica derivata dal motore Edge Alpaca/OCC, ma i dati NON sono "
        "Alpaca/OPRA e non hanno un'età OI certificata. "
        "Il NET GAMMA Serafini non viene modificato né usato per il GEX."
    )
    if not payload or not symbol:
        st.info("Carica una fotografia CSV Cboe nel modulo NET GAMMA "
                "per analizzare separatamente il GEX.")
        return
    digest = hashlib.sha256(payload).hexdigest()
    st.markdown(f"**Sottostante:** {symbol} · **Identità CSV:** {digest[:12]}")
    labels = {
        "Rilevamento automatico (blocco se IV ambigua)": "auto",
        "IV decimale · 0,20 = 20%": "decimal",
        "IV percentuale · 20 = 20%": "percent",
    }
    choice = st.selectbox(
        "Unità della volatilità implicita nel CSV",
        list(labels), key="csv_gex_iv_units",
        help="Rilevamento automatico predefinito. Se l'unità IV è ambigua, "
             "è possibile correggerla qui: l'app ricalcola da sola al cambio.",
    )
    mode = labels[choice]
    signature = (digest, symbol, mode)
    # Il report è stato preparato automaticamente prima dei Pine.
    # Qui si visualizza soltanto: nessun pulsante, rerun o secondo download.
    saved = st.session_state.get("csv_gex_last_report")
    if not saved or saved[0] != signature:
        error = st.session_state.get("csv_gex_last_error")
        if error:
            st.warning("GEX non calcolabile da questo CSV: " + error)
        else:
            st.info("GEX non disponibile per la fotografia selezionata. "
                    "Il NET GAMMA e il relativo Pine restano utilizzabili.")
        return
    info = saved[1]
    st.caption("**Calcolo automatico:** un solo CSV alimenta NET GAMMA e GEX. "
               "Il Pine include i livelli GEX quando superano i controlli di qualità.")
    st.caption(
        f"**Fonte:** CSV Cboe caricato · **Acquisizione originale:** "
        f"{info['timestamp_rome']} Roma · **Modello:** {MODEL_LABEL} · "
        f"**Quote:** non certificate · **OI:** data non documentata. "
        f"Contratti analizzati: {info['csv_contracts']} · "
        f"OI assenti: {info['oi_missing']} · IV assenti: {info['iv_missing']}."
    )
    st.caption(info["iv_note"])
    selected = st.radio("Scadenza GEX", ["0DTE", "Weekly"], horizontal=True,
                        key="csv_gex_selected_expiry")
    report = info["reports"][selected]
    st.caption(f"**{selected}** · Scadenza: {report['expiry']} · "
               f"Contratti nel CSV: {report['contracts']} · "
               f"Validi GEX (OI > 0 + IV utilizzabile): {report['valid']}")
    if report["status"] != "DIAGNOSTICO":
        st.warning("Qualità insufficiente — livelli, regime e curva GEX N/D. "
                   + report["reason"])
        metrics = st.columns(4)
        for column, name in zip(metrics, ("Call Wall", "Put Wall", "Gamma Flip", "Regime")):
            column.metric(name, "N/D")
        st.metric("NET GEX (mld USD / 1%)", "N/D")
        return
    st.warning(
        "**GEX DIAGNOSTICO, NON CERTIFICATO.** " + report["reason"] +
        " I livelli non rappresentano posizioni dealer osservate e non sono "
        "segnali operativi."
    )
    # Lo stile si applica SOLO ai valori negativi del modulo GEX,
    # non alle etichette, ai livelli NET GAMMA o ai grafici.
    st.html("""
    <style>
    [class*="st-key-csv_gex_negative_"] [data-testid="stMetricValue"],
    [class*="st-key-csv_gex_negative_"] [data-testid="stMetricValue"] * {
        color: #ff5b65 !important;
    }
    </style>
    """)
    metrics = st.columns(4)
    for column, field, label, suffix in (
        (metrics[0], "call_wall", "Call Wall", "call_wall"),
        (metrics[1], "put_wall", "Put Wall", "put_wall"),
        (metrics[2], "flip", "Gamma Flip", "flip"),
    ):
        value = report[field]
        _gex_metric(
            column, label, _number(value),
            negative=value is not None and value < 0, key=suffix,
        )
    _gex_metric(
        metrics[3], "Regime GEX modellato", report["regime"].upper(),
        negative=report["regime"].lower() == "negative", key="regime",
    )
    a, b, c = st.columns(3)
    for column, field, label, suffix in (
        (a, "net_gex", "NET GEX · mld USD / 1%", "net"),
        (b, "call_gex", "CALL GEX · mld USD / 1%", "call"),
        (c, "put_gex", "PUT GEX · mld USD / 1%", "put"),
    ):
        value = report[field]
        _gex_metric(
            column, label, f"{value/1e9:+.3f}",
            negative=value < 0, key=suffix,
        )
    st.caption(
        "Scenario prezzo: 201 punti, ±10% dallo spot; IV, OI e tempo "
        "alla scadenza T congelati. Gamma BSM r=q=0; "
        "Gamma Flip solo se la curva attraversa realmente lo zero."
    )
    st.plotly_chart(_curve_chart(report, info["spot"]), use_container_width=True,
                    key=f"csv_gex_curve_{selected}")
    with st.expander("GEX per strike · composizione Call / Put", expanded=False):
        st.plotly_chart(_strikes_chart(report), use_container_width=True,
                        key=f"csv_gex_strikes_{selected}")
        st.caption("Unità: miliardi di USD per movimento dell'1%. "
                   "Contributi Put negativi per convenzione modellistica.")
