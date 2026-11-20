"""Sessione asiatica ES 00:00–09:00 Roma; indipendente dai calcoli NET GAMMA."""
from datetime import date, datetime, timedelta, time
from html import escape
from zoneinfo import ZoneInfo
import math
import pandas as pd
import streamlit as st

ROME = ZoneInfo("Europe/Rome")


def _dark_asia_cards(entries):
    """Presentazione: schede scure coordinate con Trend Daily, senza ricalcoli."""
    cells = []
    for label, value, detail, color in entries:
        text_color = color if color in (
            "#22c55e", "#ef4444", "#f59e0b", "#f4f5f6", "#b6bcc5"
        ) else "#f4f5f6"
        detail_html = (
            '<div class="spx-asia-detail">' + escape(str(detail)) + '</div>'
            if detail else ""
        )
        cells.append(
            '<div class="spx-asia-kpi">'
            '<div class="spx-asia-label">' + escape(str(label)) + '</div>'
            '<div class="spx-asia-value" style="color:' + text_color + '">'
            + escape(str(value)) + '</div>' + detail_html + '</div>'
        )
    st.html(
        '<style>'
        '.spx-asia-card{background:#090a0c;color:#f4f5f6;border:1px solid #34363c;'
        'border-radius:13px;padding:14px 18px;margin:8px 0 12px}'
        '.spx-asia-grid{display:grid;align-items:stretch;gap:0}'
        '.spx-asia-kpi{min-width:0;padding:6px 16px;border-left:1px solid #292b30}'
        '.spx-asia-kpi:first-child{border-left:0;padding-left:0}'
        '.spx-asia-label{font-size:.82rem;color:#b6bcc5;margin-bottom:6px}'
        '.spx-asia-value{font-size:1.16rem;font-weight:700;overflow-wrap:anywhere;line-height:1.4}'
        '.spx-asia-detail{font-size:.8rem;color:#a9b4c3;line-height:1.5;margin-top:6px}'
        '@media(max-width:900px){.spx-asia-grid{grid-template-columns:repeat(2,minmax(0,1fr))!important}'
        '.spx-asia-kpi:nth-child(odd){border-left:0;padding-left:0}}'
        '@media(max-width:600px){.spx-asia-grid{grid-template-columns:1fr!important}'
        '.spx-asia-kpi{border-left:0;padding-left:0;border-top:1px solid #292b30}'
        '.spx-asia-kpi:first-child{border-top:0}}'
        '</style>'
        '<div class="spx-asia-card"><div class="spx-asia-grid" style="grid-template-columns:'
        'repeat(' + str(len(entries)) + ',minmax(0,1fr))">'
        + ''.join(cells) + '</div></div>'
    )


def _column(frame, field):
    """Seleziona solo la colonna ES=F anche con MultiIndex Yahoo."""
    if isinstance(frame.columns, pd.MultiIndex):
        for key in ((field, "ES=F"), ("ES=F", field)):
            if key in frame.columns:
                return frame[key]
        raise ValueError(f"Colonna {field} ES=F non riconosciuta.")
    if field not in frame.columns:
        raise ValueError(f"Colonna {field} mancante.")
    return frame[field]



def _recover_yahoo_5m_from_1m(target, bars, missing):
    """Ricostruisce solo barre 5m mancanti con cinque barre Yahoo 1m REALI.

    Controlli anti-invenzione: 5 timestamp consecutivi esatti; OHLC coerenti;
    almeno 3 periodi 5m condivisi con Yahoo verificati con scarto <=0.25 ES.
    Nessun riempimento/interpolazione. Il feed 1m Yahoo ha storico limitato.
    """
    if not 0 < len(missing) <= 3:
        return bars, []
    today = datetime.now(ROME).date()
    if not target <= today or (today - target).days > 6:
        return bars, []
    try:
        import yfinance as yf
        one = yf.download(
            "ES=F", start=(target - timedelta(days=1)).isoformat(),
            end=(target + timedelta(days=1)).isoformat(),
            interval="1m", auto_adjust=False, progress=False,
            threads=False, prepost=True,
        )
        if one is None or one.empty or one.index.tz is None:
            return bars, []
        one = one.copy()
        one.index = one.index.tz_convert(ROME)
        if one.index.has_duplicates:
            return bars, []
        fields = ("Open", "High", "Low", "Close")
        minute = pd.DataFrame({
            name: pd.to_numeric(_column(one, name), errors="coerce")
            for name in fields
        }, index=one.index)
        five = pd.DataFrame({
            name: pd.to_numeric(_column(bars, name), errors="coerce")
            for name in fields
        }, index=bars.index)

        def aggregate(stamp):
            times = pd.date_range(stamp, periods=5, freq="min")
            if not all(t in minute.index for t in times):
                return None
            block = minute.loc[times, list(fields)]
            if block.isna().any().any() or not all(
                    math.isfinite(float(v)) and float(v) > 0
                    for v in block.to_numpy().flat):
                return None
            if (block["High"] < block["Low"]).any():
                return None
            if ((block["Open"] > block["High"]) |
                    (block["Open"] < block["Low"]) |
                    (block["Close"] > block["High"]) |
                    (block["Close"] < block["Low"])).any():
                return None
            return {
                "Open": float(block["Open"].iloc[0]),
                "High": float(block["High"].max()),
                "Low": float(block["Low"].min()),
                "Close": float(block["Close"].iloc[-1]),
            }

        # Prima verifica che siano lo stesso contratto/feed effettivo.
        comparable = []
        for stamp in five.index:
            merged = aggregate(stamp)
            if merged is None:
                continue
            dif = max(abs(merged[f] - float(five.at[stamp, f]))
                      for f in fields)
            if not math.isfinite(dif):
                continue
            comparable.append(dif)
        if len(comparable) < 3 or max(comparable) > 0.25:
            return bars, []

        recovered = {stamp: aggregate(stamp) for stamp in missing}
        recovered = {stamp: row for stamp, row in recovered.items()
                     if row is not None}
        if not recovered:
            return bars, []
        additions = pd.DataFrame.from_dict(recovered, orient="index")
        completed = pd.concat([five, additions]).sort_index()
        if completed.index.has_duplicates:
            return bars, []
        return completed, [stamp.strftime("%H:%M") for stamp in sorted(recovered)]
    except Exception:
        # Niente correzioni se Yahoo 1m e' indisponibile o non verificabile.
        return bars, []


def _complete_higher_timeframe(target, five_minutes):
    """Certifica gli estremi Asia con barre Yahoo reali 15m, poi 30m.

    Usata soltanto quando manca almeno una 5m. Ogni barra deve essere presente
    e chiusa, compresa quella che termina alle 09:00 Roma. Verifica anche che
    massimo/minimo/close siano coerenti con le 5m effettivamente disponibili.
    Non ricostruisce le candele 5m mancanti, né la cronologia C1/P1.
    """
    import yfinance as yf

    start = datetime.combine(target, time(0, 0), ROME)
    end = datetime.combine(target, time(9, 0), ROME)
    observed_hi = pd.to_numeric(_column(five_minutes, "High"), errors="coerce")
    observed_lo = pd.to_numeric(_column(five_minutes, "Low"), errors="coerce")
    # La 5m delle 08:55 e' l'ultima barra, con close effettivo ore 09:00.
    last_five = start + timedelta(hours=8, minutes=55)
    observed_close = None
    if last_five in five_minutes.index:
        observed_close = float(pd.to_numeric(
            _column(five_minutes, "Close"), errors="coerce").loc[last_five])

    for interval, minutes in (("15m", 15), ("30m", 30)):
        try:
            raw = yf.download(
                "ES=F", start=(target - timedelta(days=1)).isoformat(),
                end=(target + timedelta(days=1)).isoformat(),
                interval=interval, auto_adjust=False, progress=False,
                threads=False, prepost=True,
            )
            if raw is None or raw.empty or raw.index.tz is None:
                continue
            raw = raw.copy()
            raw.index = raw.index.tz_convert(ROME)
            if raw.index.has_duplicates:
                continue
            expected = pd.date_range(start=start, end=end,
                                     freq=f"{minutes}min", inclusive="left")
            frame = pd.DataFrame({
                field: pd.to_numeric(_column(raw, field), errors="coerce")
                for field in ("Open", "High", "Low", "Close")
            }, index=raw.index)
            session = frame.loc[(frame.index >= start) & (frame.index < end)]
            # Il timestamp di Yahoo e' l'APERTURA della barra: per certificare
            # la chiusura delle 09:00 deve esserci anche l'ultima 08:45/08:30.
            if not session.index.equals(expected):
                continue
            if session.isna().any().any() or not all(
                math.isfinite(float(v)) and float(v) > 0
                for v in session.to_numpy().flat
            ):
                continue
            if ((session["High"] < session["Low"]) |
                (session["Open"] > session["High"]) |
                (session["Open"] < session["Low"]) |
                (session["Close"] > session["High"]) |
                (session["Close"] < session["Low"])).any():
                continue
            hi, lo, closing = (
                float(session["High"].max()),
                float(session["Low"].min()),
                float(session["Close"].iloc[-1]),
            )
            if not observed_hi.empty and observed_hi.notna().all():
                if hi < float(observed_hi.max()) - 0.25:
                    continue
            if not observed_lo.empty and observed_lo.notna().all():
                if lo > float(observed_lo.min()) + 0.25:
                    continue
            if observed_close is not None and (
                not math.isfinite(observed_close) or
                abs(closing - observed_close) > 0.25
            ):
                continue
            return {
                "high": hi, "low": lo, "close": closing,
                "bars": len(session), "expected": len(expected),
                "source": (f"Yahoo Finance ES=F · {minutes} minuti "
                           "· 00:00–09:00 Roma (copertura completa)"),
                "resolution": f"{minutes}m",
            }
        except Exception:
            # Se Yahoo non fornisce una catena 15m affidabile, prova 30m.
            continue
    return None


@st.cache_data(ttl=120, max_entries=90, show_spinner=False)
def asian_session(target: date):
    """5m per cronologia C1/P1; 15m/30m completi certificano gli estremi se manca una 5m."""
    import yfinance as yf

    now = datetime.now(ROME)
    if target > now.date() or (target == now.date() and now.time() < time(9, 0)):
        raise ValueError("La sessione asiatica non è ancora terminata alle 09:00.")
    if target < now.date() - timedelta(days=55):
        raise ValueError("Storico ES a 5 minuti non disponibile per questa data.")
    frame = yf.download(
        "ES=F", start=(target - timedelta(days=1)).isoformat(),
        end=(target + timedelta(days=1)).isoformat(),
        interval="5m", auto_adjust=False, progress=False,
        threads=False, prepost=True,
    )
    if frame is None or frame.empty or frame.index.tz is None:
        raise ValueError("Yahoo non ha restituito barre intraday ES valide.")
    frame = frame.copy()
    frame.index = frame.index.tz_convert(ROME)
    start = datetime.combine(target, time(0, 0), ROME)
    end = datetime.combine(target, time(9, 0), ROME)
    expected = pd.date_range(start=start, end=end, freq="5min", inclusive="left")
    bars = frame[(frame.index >= start) & (frame.index < end)].copy()
    if bars.index.has_duplicates:
        raise ValueError("Timestamp ES duplicati nella sessione asiatica.")
    missing = expected.difference(bars.index)
    extra = bars.index.difference(expected)
    # Gli estremi non richiedono le singole 5m: prima verifica un aggregato
    # COMPLETO 15m o 30m, solo se la cronologia 5m presenta una lacuna.
    higher_range = (_complete_higher_timeframe(target, bars)
                    if len(missing) and not len(extra) else None)
    yahoo_1m_recovered = []
    if len(missing) and not len(extra) and higher_range is None:
        bars, yahoo_1m_recovered = _recover_yahoo_5m_from_1m(
            target, bars, missing)
        missing = expected.difference(bars.index)
        extra = bars.index.difference(expected)
    # Una candela 5m assente NON viene mai inventata.
    source = "Yahoo Finance ES=F · 5 minuti (integrazione 1m validata se disponibile)"
    # Fino a 3 lacune: rendi gli estremi PROVVISORI, non bloccare anche la chiusura.
    if len(extra) or (higher_range is None and
                      (len(missing) > 3 or len(bars) < len(expected) - 3)):
        raise ValueError(
            f"Sessione incompleta: {len(bars)}/{len(expected)} barre; "
            f"{len(missing)} mancanti, {len(extra)} fuori griglia."
        )
    if expected[-1] not in bars.index and higher_range is None:
        raise ValueError("Manca la barra conclusiva 08:55–09:00: chiusura non verificabile.")
    # Le barre mancanti non consentono di certificare gli estremi di tutta la sessione.
    high = pd.to_numeric(_column(bars, "High"), errors="coerce")
    low = pd.to_numeric(_column(bars, "Low"), errors="coerce")
    close = pd.to_numeric(_column(bars, "Close"), errors="coerce")
    if not (high.notna().all() and low.notna().all() and close.notna().all()):
        raise ValueError("Barre OHLC con valori mancanti.")
    if not all(math.isfinite(float(v)) and float(v) > 0
               for col in (high, low, close) for v in col):
        raise ValueError("Barre OHLC con valori non validi.")
    if (high < low).any() or (close > high).any() or (close < low).any():
        raise ValueError("Barre OHLC incoerenti.")
    hi, lo, last = float(high.max()), float(low.min()), float(close.iloc[-1])
    if higher_range is not None:
        # Il range e' verificato dal timeframe completo.
        hi, lo, last = (higher_range[k] for k in ("high", "low", "close"))
        source = higher_range["source"]
    return {
        "high": hi, "low": lo, "close": last,
        "bars": higher_range["bars"] if higher_range else len(bars),
        "expected": higher_range["expected"] if higher_range else len(expected),
        "missing_times": ([] if higher_range else
                          [t.strftime("%H:%M") for t in missing]),
        "yahoo_1m_recovered_times": yahoo_1m_recovered,
        "source": source,
    }


def asia_range_reading(result):
    """Lettura descrittiva della chiusura 09:00 rispetto al RANGE Asia.

    Non produce segnali trading. Estremi provvisori se mancano barre.
    """
    hi, lo, price = (float(result[k]) for k in ("high", "low", "close"))
    if not all(math.isfinite(v) for v in (hi, lo, price)):
        raise ValueError("Estremi o chiusura Asia non finiti")
    if not (lo <= price <= hi) or hi <= lo:
        raise ValueError("Range Asia incoerente o di ampiezza nulla")
    ratio = (price - lo) / (hi - lo)
    if ratio < 1.0 / 3.0:
        zone = "FASCIA BASSA"
        reading = "Chiusura vicina alla parte bassa del range: elemento di debolezza relativa."
        color = "#f59e0b"
    elif ratio > 2.0 / 3.0:
        zone = "FASCIA ALTA"
        reading = "Chiusura vicina alla parte alta del range: elemento di forza relativa."
        color = "#22c55e"
    else:
        zone = "FASCIA CENTRALE"
        reading = "Chiusura nella parte centrale del range: nessuna prevalenza dal solo range."
        color = "#f59e0b"
    provisional = bool(result.get("missing_times"))
    return {
        "status": "PROVVISORIO" if provisional else "VALIDO",
        "zone": zone,
        "verdict": "CHIUSURA 09:00 IN " + zone + " DEL RANGE ASIA",
        "reading": reading,
        "close_position_pct": round(100.0 * ratio, 2),
        "range_points": round(hi - lo, 2),
        "distance_from_low": round(price - lo, 2),
        "distance_from_high": round(hi - price, 2),
        "extremes_provisional": provisional,
        "color": color,
        "scope": ("Lettura descrittiva della sessione asiatica, "
                  "non è un segnale operativo LONG/SHORT."),
    }


def close_at_nine(target: date):
    """Compatibilita' con la versione precedente."""
    result = asian_session(target)
    return {"price": result["close"], "source": result["source"],
            "time": target.isoformat() + " 09:00"}



def render(target: date):
    st.markdown("**Sessione asiatica — 00:00–09:00 (Roma)**")
    try:
        result = asian_session(target)
    except Exception as exc:
        st.info(f"Dati sessione asiatica non disponibili: {exc}")
        return

    hi, lo, price = result["high"], result["low"], result["close"]
    _dark_asia_cards([
        ("Massimo Asia", f"{hi:,.2f}", "ES · sessione 00:00–09:00 Roma", "#f4f5f6"),
        ("Minimo Asia", f"{lo:,.2f}", "ES · sessione 00:00–09:00 Roma", "#f4f5f6"),
        ("Chiusura ore 09:00", f"{price:,.2f}", "Ultima barra verificata", "#f4f5f6"),
    ])
    if result["missing_times"]:
        missing_count = len(result["missing_times"])
        description = ("manca la barra delle " if missing_count == 1
                       else "mancano le barre delle ")
        message = ("Massimo e minimo PROVVISORI: " + description +
                   ", ".join(result["missing_times"]) +
                   f" ({result['bars']}/{result['expected']} barre). "
                   "Chiusura delle 09:00 verificata sulla barra finale; "
                   "gli estremi potrebbero cambiare.")
        st.markdown(
            f'<span style="color:#ef4444;font-size:0.88rem">{message}</span>',
            unsafe_allow_html=True,
        )
    else:
        st.caption(f"{result['source']} · {result['bars']}/{result['expected']} barre verificate.")
    if result.get("yahoo_1m_recovered_times"):
        st.caption(
            "Yahoo ES=F: candele 5m mancanti recuperate da cinque barre "
            "reali a 1 minuto ciascuna ("
            + ", ".join(result["yahoo_1m_recovered_times"])
            + "), dopo verifica OHLC su altre barre comuni."
        )

    # Lettura autonoma del range Asia.
    reading = asia_range_reading(result)
    _dark_asia_cards([
        ("Responso Asia ore 09:00", reading["zone"], reading["verdict"], reading["color"]),
        ("Chiusura nel range Asia", f'{reading["close_position_pct"]:.1f}%',
         f'{reading["distance_from_low"]:.2f} pt sopra il minimo · '
         f'{reading["distance_from_high"]:.2f} pt sotto il massimo', "#f4f5f6"),
    ])
    st.caption(
        reading["reading"] + " " + reading["scope"] +
        (" Estremi provvisori per barre mancanti."
         if reading["extremes_provisional"] else "")
    )
def render_auto(target: date):
    """Aggiorna soltanto il Quadro 09:00, senza ricalcolare il NET GAMMA."""
    now = datetime.now(ROME)
    live = target == now.date() and now.time() < time(9, 45)
    if not live:
        render(target)
        return

    @st.fragment(run_every="2min")
    def _asian_live_fragment():
        current = datetime.now(ROME)
        if current.time() >= time(9, 45):
            st.rerun()
        render(target)
        st.caption("Sessione asiatica: aggiornamento automatico ogni 2 minuti "
                   "fino alle 09:45, senza ricaricare l'app.")
    _asian_live_fragment()
