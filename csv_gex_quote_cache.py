"""Un'unica quotazione ES verificata per grafici NET GAMMA e curva GEX.

Yahoo resta la fonte prioritaria. Se Yahoo non restituisce una osservazione
entro 90 minuti, prova il Massive Futures 5m già configurato nell'app.
Il recupero Massive è opzionale e non richiede nuovi abbonamenti: se il
piano non autorizza il dato, resta N/D e viene dichiarato. Nessuna stima.
"""
import streamlit as st

from csv_gex_es_quote import fetch_es_quote
from massive_es_last_quote import fetch_massive_es_quote


def _failure_label(exc):
    """Messaggio diagnostico essenziale, senza URL autenticati o segreti."""
    status = getattr(getattr(exc, "response", None), "status_code", None)
    if status is not None:
        return f"{type(exc).__name__} HTTP {status}"
    return type(exc).__name__


def resolve_es_quote(yahoo_fetch, massive_fetch, massive_api_key):
    """Fonte con ultimo prezzo reale verificabile, altrimenti N/D esplicito.

    Funzione testabile offline; non inventa prezzi e non assegna la
    data del download all'orario della quotazione.
    """
    try:
        yahoo = yahoo_fetch()
        if isinstance(yahoo, dict) and yahoo.get("price") is not None:
            return yahoo
        yahoo_error = (yahoo or {}).get("error") or "nessuna barra <=90 min"
    except Exception as exc:
        yahoo_error = _failure_label(exc)

    if not massive_api_key:
        reason = "Massive: MASSIVE_API_KEY assente nell'app"
    else:
        try:
            fallback = massive_fetch(api_key=massive_api_key)
            if isinstance(fallback, dict) and fallback.get("price") is not None:
                return fallback
            reason = "Massive: nessuna barra 5m verificabile"
        except Exception as exc:
            reason = "Massive: " + _failure_label(exc)
            if isinstance(exc, ValueError):
                reason = "Massive: " + str(exc)[:180]

    return {
        "price": None,
        "source": "N_D",
        "symbol": "ES",
        "observed_utc": None,
        "age_minutes": None,
        "error": f"Yahoo: {yahoo_error}; {reason}",
    }


@st.cache_data(show_spinner=False, max_entries=5, ttl=60)
def cached_es_quote():
    """Ultima osservazione ES; massimo 90 min per entrambe le fonti."""
    try:
        api_key = str(st.secrets.get("MASSIVE_API_KEY", "")).strip()
    except Exception:
        api_key = ""
    return resolve_es_quote(fetch_es_quote, fetch_massive_es_quote, api_key)


_cached_es_quote = cached_es_quote
