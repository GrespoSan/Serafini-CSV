"""Confronto facoltativo tra NET GAMMA statico Cboe e candele REALI Yahoo 5m.

Nessun download se il toggle e' spento. I prezzi Gamma vengono SOLO convertiti
sull'asse Y con il rapporto/basis gia' calcolato dal modulo chiamante.
Non usa il prezzo intraday per ricalcolare il NET GAMMA, né genera livelli.
"""
from datetime import date, datetime, timedelta, time, timezone
from zoneinfo import ZoneInfo
import math
import re

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

ROME = ZoneInfo("Europe/Rome")
UTC = timezone.utc
FUTURES = {"ES=F", "RTY=F", "YM=F", "GC=F", "CL=F"}


@st.cache_data(ttl=300, show_spinner=False, max_entries=24)
def load_closed_candles(ticker: str, target_day: date):
    """Yahoo 5m, timestamp della CHIUSURA, senza barre future o incomplete."""
    import yfinance as yf

    if ticker not in FUTURES and not re.fullmatch(r"[A-Z][A-Z0-9.\-]{0,14}", ticker):
        raise ValueError("Ticker Yahoo non consentito.")
    if not isinstance(target_day, date):
        raise ValueError("Data di confronto non valida.")
    start = datetime.combine(target_day, time.min, tzinfo=ROME)
    end = start + timedelta(days=1)
    now = datetime.now(UTC)
    if now <= start.astimezone(UTC):
        raise ValueError("La giornata di confronto non e' ancora iniziata.")
    if (now - start.astimezone(UTC)).days > 59:
        raise ValueError("Yahoo 5m non copre questa data: limite circa 59 giorni.")

    raw = yf.download(
        ticker, start=(target_day - timedelta(days=1)).isoformat(),
        end=(target_day + timedelta(days=2)).isoformat(),
        interval="5m", prepost=True, auto_adjust=False,
        progress=False, threads=False,
    )
    if raw is None or raw.empty or raw.index.tz is None:
        raise ValueError(f"Barre {ticker} 5m non disponibili da Yahoo.")
    raw = raw.copy()
    if isinstance(raw.columns, pd.MultiIndex):
        # yfinance restituisce talvolta (prezzo, ticker) oppure (ticker, prezzo).
        wanted = {"Open", "High", "Low", "Close"}
        for depth in range(raw.columns.nlevels):
            layer = raw.columns.get_level_values(depth)
            if wanted.issubset(set(layer)):
                raw.columns = layer
                break
    fields = ("Open", "High", "Low", "Close")
    if any(field not in raw.columns for field in fields):
        raise ValueError("Candele Yahoo senza tutti i campi OHLC.")
    closes_at = raw.index.tz_convert(ROME) + pd.Timedelta(minutes=5)
    candles = pd.DataFrame({
        field.lower(): pd.to_numeric(raw[field], errors="coerce").to_numpy()
        for field in fields
    }, index=closes_at)
    now_rome = pd.Timestamp(now).tz_convert(ROME)
    candles = candles.loc[
        (candles.index >= start) & (candles.index < end)
        & (candles.index <= now_rome)
    ].dropna(subset=[field.lower() for field in fields])
    if candles.empty:
        raise ValueError("Nessuna candela 5m conclusa disponibile nella giornata.")
    candles = candles[
        (candles["high"] >= candles["low"])
        & (candles["low"] <= candles["open"])
        & (candles["open"] <= candles["high"])
        & (candles["low"] <= candles["close"])
        & (candles["close"] <= candles["high"])
        & (candles[["open", "high", "low", "close"]] > 0).all(axis=1)
    ]
    if candles.empty:
        raise ValueError("Candele 5m prive di OHLC coerenti.")
    candles.index.name = "bar_close"
    return candles.reset_index()


def comparison_chart(group, candles, *, strike_field: str, gamma_field: str,
                     source_name: str, future_name: str, group_name: str,
                     price_scale=1.0, price_shift=0.0,
                     reference_close=None):
    """Due grafici affiancati, asse Y di prezzo comune, NET GAMMA invariato."""
    scale, shift = float(price_scale), float(price_shift)
    if not (math.isfinite(scale) and scale > 0 and math.isfinite(shift)):
        raise ValueError("Rapporto o differenziale prezzo non valido.")
    rows = group.get("rows") or []
    if not rows:
        raise ValueError("Il profilo Gamma selezionato non ha strike.")
    prices = [float(row[strike_field]) * scale + shift for row in rows]
    gamma = [float(row[gamma_field]) for row in rows]
    if not all(math.isfinite(v) and v > 0 for v in prices):
        raise ValueError("Strike convertiti non validi.")
    if not all(math.isfinite(v) for v in gamma):
        raise ValueError("NET GAMMA non valido.")
    low = min(min(prices), float(candles["low"].min()))
    high = max(max(prices), float(candles["high"].max()))
    if reference_close is not None:
        close_level = float(reference_close) * scale + shift
        if not math.isfinite(close_level) or close_level <= 0:
            raise ValueError("Close di riferimento non valido.")
        low, high = min(low, close_level), max(high, close_level)
    else:
        close_level = None
    padding = max((high - low) * 0.025, max(abs(high), 1.0) * 0.0001)
    ordered = sorted(set(prices))
    steps = [b - a for a, b in zip(ordered, ordered[1:]) if b > a]
    thickness = min(min(steps) * .72, max(high - low, 1) * 0.011) if steps else max(high - low, 1) * .008
    fig = make_subplots(
        rows=1, cols=2, shared_yaxes=True,
        column_widths=[.40, .60], horizontal_spacing=.04,
        subplot_titles=(f"NET GAMMA {group_name}", f"PREZZO {future_name} · 5 minuti"),
    )
    fig.add_trace(go.Bar(
        x=gamma, y=prices, width=thickness, orientation="h",
        marker_color=["#21cb82" if v >= 0 else "#f34e59" for v in gamma],
        customdata=[float(row[strike_field]) for row in rows],
        hovertemplate=(
            f"{future_name} %{{y:,.2f}}<br>Strike {source_name} "
            "%{customdata:,.2f}<br>NET GAMMA %{x:+.6f}<extra></extra>"
        ), name="NET GAMMA", showlegend=False,
    ), row=1, col=1)
    fig.add_trace(go.Candlestick(
        x=candles["bar_close"],
        open=candles["open"], high=candles["high"],
        low=candles["low"], close=candles["close"],
        increasing_line_color="#21b77c", decreasing_line_color="#e65353",
        name=future_name, showlegend=False,
    ), row=1, col=2)
    for col in (1, 2):
        fig.update_yaxes(range=[low - padding, high + padding], row=1, col=col)
        if close_level is not None:
            fig.add_hline(y=close_level, line_color="#f0cc65",
                          line_width=1.4, line_dash="dash", row=1, col=col)
    fig.update_layout(
        height=700, margin=dict(l=38, r=20, t=64, b=45),
        template="plotly_dark", barmode="relative", showlegend=False,
    )
    fig.update_yaxes(title_text=f"Prezzo {future_name}", row=1, col=1)
    fig.update_xaxes(title_text="NET GAMMA originale", row=1, col=1)
    fig.update_xaxes(title_text="Ora Roma · candele 5m chiuse",
                     rangeslider_visible=False, row=1, col=2)
    return fig


def render_optional_compare(*, label: str, key: str, yahoo_ticker: str,
                            target_day: date, groups: dict, strike_field: str,
                            gamma_field: str, source_name: str,
                            price_name: str, price_scale=1.0,
                            price_shift=0.0, reference_close=None,
                            available=True, unavailable_reason=""):
    """Widget comune: nessun accesso ai prezzi senza scelta esplicita."""
    st.subheader(f"Confronto NET GAMMA / candele {label}")
    enabled = st.toggle(
        f"Mostra NET GAMMA a sinistra e candele {price_name} a destra",
        value=False, key=f"gamma_candle_compare_{key}",
    )
    if not enabled:
        return
    if not available:
        st.info(unavailable_reason or "Conversione dei livelli non verificata.")
        return
    options = [name for name, group in groups.items() if group.get("rows")]
    if not options:
        st.info("Nessun profilo Gamma utilizzabile per il confronto.")
        return
    selected = st.radio(
        "Profilo da confrontare", options,
        horizontal=True, key=f"gamma_candle_profile_{key}",
    )
    try:
        with st.spinner(f"Lettura candele {yahoo_ticker} Yahoo a 5 minuti..."):
            candles = load_closed_candles(yahoo_ticker, target_day)
        figure = comparison_chart(
            groups[selected], candles, strike_field=strike_field,
            gamma_field=gamma_field, source_name=source_name,
            future_name=price_name, group_name=selected,
            price_scale=price_scale, price_shift=price_shift,
            reference_close=reference_close,
        )
        st.plotly_chart(figure, use_container_width=True,
                        key=f"gamma_price_chart_{key}_{selected}_{target_day}")
        st.caption(
            f"Candele Yahoo {yahoo_ticker} a 5 minuti chiusi, "
            f"giornata {target_day:%d/%m/%Y} (Roma). "
            "Prezzo e NET GAMMA condividono l'asse Y; "
            "gli strike sono originali e il Gamma non viene ricalcolato. "
            "Il continuo Yahoo puo' differire dal TradingView dopo il rollover."
        )
    except (ValueError, TypeError, KeyError, OSError, OverflowError) as exc:
        st.warning(f"Confronto candele non disponibile: {str(exc)[:230]}. "
                   "Il grafico NET GAMMA originale rimane utilizzabile.")
