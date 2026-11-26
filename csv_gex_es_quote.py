"""ES futures quote from Yahoo Chart, delayed/indicative availability only.

On the GEX chart this is a DIRECT futures price marker, NEVER a SPX
spot plus basis estimate. Primary: explicit front quarterly CME contract.
Fallback: ES=F continuous Yahoo future (always prominently labeled).
Network errors and stale quotes return N/D; no invented price/timestamp.
"""
from __future__ import annotations

import json
import math
from datetime import date, datetime, timedelta, timezone
from urllib.parse import quote
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

ROME=ZoneInfo("Europe/Rome")
NY=ZoneInfo("America/New_York")
MONTH_CODES={3:"H",6:"M",9:"U",12:"Z"}


def _third_friday(year, month):
    d=date(year,month,1)
    return d+timedelta(days=(4-d.weekday())%7+14)


def front_symbol(on_date: date):
    """Conservative quarterly rollover 8 calendar days before expiry."""
    for year in range(on_date.year,on_date.year+3):
        for month,code in MONTH_CODES.items():
            third=_third_friday(year,month)
            if on_date < third-timedelta(days=8):
                return f"ES{code}{year%100:02d}.CME"
    raise ValueError("Nessun contratto trimestrale ES individuato")


# A holiday/session break must not turn a genuine delayed quote into a
# fabricated current price. Accept at most 36h and label anything older
# than 90 minutes explicitly as the LAST AVAILABLE observation.
RECENT_MINUTES = 90
MAX_LAST_AVAILABLE_MINUTES = 36 * 60


def quote_age_label(quote):
    """Label entirely grounded in original Yahoo price/time metadata."""
    if not isinstance(quote, dict) or quote.get("price") is None:
        return "Prezzo ES N/D — Yahoo non fornisce una quotazione utilizzabile"
    age = quote.get("age_minutes")
    if age is None:
        return "Prezzo ES N/D — età osservazione non certificata"
    if age <= RECENT_MINUTES:
        return "Ultimo prezzo ES Yahoo (potenzialmente ritardato)"
    return "Ultima quotazione ES Yahoo disponibile — NON attuale"


def _verified_observation(stamp_s, price, now):
    try:
        value = float(price)
        stamp = datetime.fromtimestamp(int(stamp_s), timezone.utc)
        age = (now - stamp).total_seconds() / 60
        if math.isfinite(value) and value > 0 and -2 <= age <= MAX_LAST_AVAILABLE_MINUTES:
            return stamp, value
    except (TypeError, OverflowError, ValueError, OSError):
        pass
    return None


def parse_chart(body: bytes, ticker: str, now: datetime):
    """Accept real time-stamped ES prices, with separate age classification.

    During market closures a genuine price can be older than 90m.
    Reject >36h, missing timestamps, mismatched ticker and guessed prices.
    """
    doc = json.loads(body)
    results = (doc.get("chart") or {}).get("result") or []
    if not results:
        raise ValueError("Yahoo non restituisce una serie ES")
    item = results[0]
    meta = item.get("meta") or {}
    actual = meta.get("symbol")
    if actual and str(actual).upper() != ticker.upper():
        raise ValueError("Simbolo Yahoo differente dal future richiesto")
    rows = (((item.get("indicators") or {}).get("quote") or [{}])[0]
            .get("close") or [])
    times = item.get("timestamp") or []
    pairs = []
    for t, price in zip(times, rows):
        valid = _verified_observation(t, price, now)
        if valid is not None:
            pairs.append(valid)

    # On holidays Yahoo can publish only the last regularMarketPrice.
    # It is allowed ONLY with its own Unix market timestamp, never with
    # fetch time, previousClose or synthetic SPX+ES basis.
    if not pairs:
        from_meta = _verified_observation(
            meta.get("regularMarketTime"),
            meta.get("regularMarketPrice"),
            now,
        )
        if from_meta is not None:
            pairs.append(from_meta)
    if not pairs:
        raise ValueError(
            "Prezzo ES senza timestamp utilizzabile nelle ultime 36 ore"
        )

    stamp, price = max(pairs, key=lambda x: x[0])
    age = round(max((now - stamp).total_seconds() / 60, 0.0), 1)
    recent = age <= RECENT_MINUTES
    return {
        "price": round(price, 4),
        "symbol": ticker,
        "source": "YAHOO_FINANCE_CHART",
        "observed_utc": stamp.isoformat(),
        "observed_rome": stamp.astimezone(ROME).strftime("%d/%m/%Y %H:%M:%S"),
        "age_minutes": age,
        "quote_status": "RECENT" if recent else "LAST_AVAILABLE",
        "delayed_label": (
            "Yahoo Finance · quotazione potenzialmente ritardata"
            if recent else
            "Yahoo Finance · ultima quotazione disponibile, NON attuale"
        ),
        "contract_kind": "EXPLICIT" if ticker != "ES=F" else "CONTINUOUS",
    }


def fetch_es_quote(*, now=None, request=None):
    """Prefer genuine recent ES; on closed markets return labeled last quote.

    Try explicit front quarterly and Yahoo continuous ES=F on two Yahoo
    hosts. Never mix contract prices with a synthetic SPX basis.
    """
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("Ora senza fuso")
    on = now.astimezone(NY).date()
    primary = front_symbol(on)
    failures = []
    best_old = None
    for host in ("query1.finance.yahoo.com", "query2.finance.yahoo.com"):
        for symbol in (primary, "ES=F"):
            url = (
                f"https://{host}/v8/finance/chart/"
                f"{quote(symbol, safe='')}?range=5d&interval=1m"
            )
            try:
                if request:
                    body = request(url)
                else:
                    req = Request(url, headers={
                        "User-Agent": "Mozilla/5.0",
                        "Accept": "application/json",
                    })
                    with urlopen(req, timeout=7) as response:
                        body = response.read(2_000_001)
                if not isinstance(body, bytes) or len(body) > 2_000_000:
                    raise ValueError("Dati Yahoo non validi o troppo grandi")
                result = parse_chart(body, symbol, now)
                result["preferred_contract"] = primary
                if result["quote_status"] == "RECENT":
                    return result
                if (best_old is None or
                        result["age_minutes"] < best_old["age_minutes"]):
                    best_old = result
            except Exception as exc:
                failures.append(f"{symbol}@{host}: {type(exc).__name__}")

        # If a real market-last quote was recovered, don't delay the
        # app for another host just to get an equivalent old quote.
        if best_old is not None:
            break
    if best_old is not None:
        return best_old
    return {
        "price": None,
        "source": "YAHOO_FINANCE_CHART",
        "symbol": primary,
        "observed_utc": None,
        "age_minutes": None,
        "quote_status": "N_D",
        "error": (
            "Nessuna quotazione ES con timestamp verificato nelle ultime "
            "36 ore (" + "; ".join(failures) + ")"
        ),
    }
