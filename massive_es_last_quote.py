"""Prezzo ES indicativo da Massive Futures 5min, solo fallback di mercato.

Riutilizza MASSIVE_API_KEY e il contratto trimestrale già presenti
nell'app. NON usa la barra Daily (chiusura storica); prende l'ultima
barra 5m COMPLETATA con timestamp originale verificabile e <=90 minuti.
Se non autorizzato, manca la chiave o i dati sono vecchi: N/D.
Non influenza NET GAMMA, GEX, basis ES/SPX, né esportazioni Pine.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import math
from zoneinfo import ZoneInfo

import requests

from mercati.quarterly_contract import quarterly_contract


ROME = ZoneInfo("Europe/Rome")
NEW_YORK = ZoneInfo("America/New_York")
SOURCE = "MASSIVE_FUTURES_5MIN"


def parse_massive_es_5min(payload, *, contract, now):
    """Valida ultimo close di barra futures chiusa del medesimo contratto."""
    if not isinstance(now, datetime) or now.tzinfo is None:
        raise ValueError("Orologio senza fuso")
    if not isinstance(payload, dict) or payload.get("status") not in ("OK", "DELAYED"):
        raise ValueError("Massive Futures: risposta non autorizzata o stato invalido")
    rows = payload.get("results")
    if not isinstance(rows, list) or not rows or payload.get("next_url"):
        raise ValueError("Massive Futures: barre 5m assenti o risposta incompleta")

    now_utc = now.astimezone(timezone.utc)
    accepted = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        if item.get("ticker") not in (None, contract):
            raise ValueError("Massive Futures: contratto diverso da quello richiesto")
        try:
            tick = item["window_start"]
            if isinstance(tick, bool) or not isinstance(tick, int) or tick < 10**17:
                continue
            start = datetime.fromtimestamp(tick / 1e9, timezone.utc)
            complete = start + timedelta(minutes=5)
            age = (now_utc - complete).total_seconds() / 60
            op, hi, lo, price = (
                float(item[key]) for key in ("open", "high", "low", "close")
            )
            if (not all(math.isfinite(v) and v > 0 for v in (op, hi, lo, price))
                    or not (lo <= op <= hi and lo <= price <= hi)
                    or not 0 <= age <= 90):
                continue
            accepted.append((complete, price, age))
        except (KeyError, TypeError, ValueError, OSError, OverflowError):
            continue
    if not accepted:
        raise ValueError("Massive Futures: nessuna barra ES completa entro 90 minuti")
    observed, price, age = max(accepted, key=lambda row: row[0])
    return {
        "price": round(price, 4),
        "symbol": contract,
        "source": SOURCE,
        "observed_utc": observed.isoformat(),
        "observed_rome": observed.astimezone(ROME).strftime("%d/%m/%Y %H:%M:%S"),
        "age_minutes": round(age, 1),
        "contract_kind": "EXPLICIT",
        "delayed_label": (
            "Massive Futures · close ultima barra ES 5m chiusa"
            " (potenzialmente ritardata)"
        ),
        "provider_status": payload["status"],
    }


def fetch_massive_es_quote(*, api_key, now=None, get=None):
    """Fallback opzionale: UNA richiesta Massive 5m con chiave già esistente.

    Nessuna nuova subscription: accesso subordinato al piano Streamlit
    MASSIVE_API_KEY. Il contratto segue l'identica logica del Trend Daily.
    """
    if not str(api_key or "").strip():
        raise ValueError("Massive Futures: MASSIVE_API_KEY non configurata")
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("Data richiesta senza fuso")
    contract = quarterly_contract("ES", now.astimezone(NEW_YORK).date())["ticker"]
    params = {
        "resolution": "5min",
        "window_start.gte": (now.astimezone(timezone.utc).date()
                             - timedelta(days=2)).isoformat(),
        "window_start.lte": now.astimezone(timezone.utc).date().isoformat(),
        "sort": "window_start.asc",
        "limit": 750,
    }
    getter = get or requests.get
    response = getter(
        "https://api.massive.com/futures/v1/aggs/" + contract,
        params=params,
        headers={
            "Authorization": "Bearer " + str(api_key),
            "Accept": "application/json",
        },
        timeout=(3, 8),
    )
    response.raise_for_status()
    return parse_massive_es_5min(response.json(), contract=contract, now=now)
