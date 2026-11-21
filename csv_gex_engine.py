"""GEX Edge-style autonomo per CSV Cboe, matematica originale del motore Edge.

Sorgente del modello puro: GrespoSan/SPX-Edge-GEX-Lab/gexlab/engine/gex.py
Modello: gamma BSM r=q=0, Call + / Put -, OI * 100 * S^2 * 0.01.
Il CSV NON e' un feed Alpaca/OPRA: OI date e quote clock non certificati.
Il modulo non usa rete, secrets, storage o servizio GEX remoto.
"""
from __future__ import annotations

import csv
import hashlib
import io
import math
from collections import Counter
from datetime import datetime, timedelta, date, timezone
from zoneinfo import ZoneInfo

from cboe_csv_import import csv_to_snapshot, _get_csv_fields, InvalidCboeCSV
from csv_gex_core import gex, config
from csv_gex_core.calendar import Session, TradingCalendar, NY
from csv_gex_core.models import Contract, parse_occ
from volatility_levels import weekly_expiry

ROME = ZoneInfo("Europe/Rome")
UTC = timezone.utc
INDEX_AM_ROOTS = frozenset({"SPX", "NDX", "RUT", "DJX"})
INDEX_PM_ROOTS = frozenset({"SPXW", "NDXP", "NDXW", "RUTW", "DJXW"})
EMPTY = frozenset({"", "-", "--", "—", "N/A"})
GEX_SOURCE = "CBOE_CSV_MANUAL_USER_EXPORT"
MODEL_LABEL = "Edge GEX 1.1 (BSM+OI, Call+/Put−) · diagnostico"


def _raw_field_presence(blob: bytes, accepted: set[str]) -> dict[str, dict[str, bool]]:
    """Distingue gli OI/IV assenti da zero, che il parser NET GAMMA normalizza."""
    try:
        text = blob.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = blob.decode("cp1252")
    rows = list(csv.reader(io.StringIO(text)))
    start, _, columns = _get_csv_fields(rows)
    presence = {}
    for row in rows[start + 1:]:
        for side in ("call", "put"):
            col = columns[side]
            idx = col["code"]
            if idx >= len(row):
                continue
            symbol = row[idx].strip().replace(" ", "").lstrip("^").upper()
            if symbol not in accepted:
                continue
            oi_idx = col["oi"]
            iv_idx = col.get("iv")
            presence[symbol] = {
                "oi": oi_idx < len(row) and row[oi_idx].strip().upper() not in EMPTY,
                "iv": iv_idx is not None and iv_idx < len(row)
                      and row[iv_idx].strip().upper() not in EMPTY,
            }
    return presence


def _iv_normalization(options: list[dict], present: dict, mode: str) -> tuple[str | None, str]:
    """Non indovina IV ambigue: 0.20 (decimale) vs 20 (percentuale)."""
    if mode not in {"auto", "decimal", "percent"}:
        raise ValueError("Formato IV sconosciuto.")
    if mode == "decimal":
        return "decimal", "Unità IV dichiarata manualmente: decimale."
    if mode == "percent":
        return "percent", "Unità IV dichiarata manualmente: percentuale."
    values = [
        float(o["iv"]) for o in options
        if present.get(o["option"], {}).get("iv")
        and isinstance(o.get("iv"), (float, int))
        and math.isfinite(float(o["iv"])) and float(o["iv"]) > 0
    ]
    if not values:
        return None, "Il CSV non contiene valori IV utilizzabili."
    if all(0.01 <= v <= 1.0 for v in values):
        return "decimal", "Formato IV rilevato: decimale (es. 0,20)."
    if all(10.0 <= v <= 500.0 for v in values):
        return "percent", "Formato IV rilevato: percentuale (es. 20 = 20%)."
    return None, (
        "Unità IV ambigua o mista: selezionare esplicitamente Decimale o "
        "Percentuale. Nessuna conversione presunta."
    )


def _calendar(captured: datetime) -> TradingCalendar:
    """Calendario NYSE per chiusure e festivi; proxy dichiarato per Cboe options."""
    import exchange_calendars as xcals
    nyday = captured.astimezone(NY).date()
    begin, end = nyday - timedelta(days=10), nyday + timedelta(days=30)
    exchange = xcals.get_calendar("XNYS", start=begin, end=end)
    sessions = {}
    for label, row in exchange.schedule.iterrows():
        d = label.date()
        sessions[d] = Session(
            d, row["open"].tz_convert(NY).time(),
            row["close"].tz_convert(NY).time(),
        )
    if not sessions:
        raise ValueError("Calendario XNYS vuoto: scadenze non determinabili.")
    return TradingCalendar(sessions, "exchange_calendars:XNYS", (begin, end))


def _target_expiries(captured: datetime, cal: TradingCalendar) -> dict[str, date]:
    """0DTE = prossima sessione non conclusa; Weekly = venerdi' secondo Serafini."""
    if captured.tzinfo is None:
        raise ValueError("Timestamp di acquisizione senza fuso.")
    candidates = sorted(d for d in cal.sessions if cal.close_dt(d) > captured
                        and d >= captured.astimezone(NY).date())
    if not candidates:
        raise ValueError("Nessuna sessione USA successiva documentata.")
    day = candidates[0]
    return {"0DTE": day, "Weekly": weekly_expiry(day)}


def _from_snapshot(doc: dict, presence: dict, unit: str | None) -> list[Contract]:
    """Preserva contratti OCC. Non inventa IV e OI mancanti."""
    out = []
    seen = set()
    for option in doc["data"]["options"]:
        name = str(option["option"]).strip().replace(" ", "")
        if name in seen:
            raise ValueError("OCC duplicato nel CSV.")
        seen.add(name)
        occ = parse_occ(name)
        oi = option.get("open_interest")
        reported = presence.get(name, {})
        if not reported.get("oi"):
            oi = None
        elif (not isinstance(oi, (int, float)) or not math.isfinite(float(oi))
              or oi < 0 or int(oi) != oi):
            raise ValueError("Open Interest OCC non intero o non valido.")
        else:
            oi = int(oi)
        raw_iv = option.get("iv")
        iv = None
        if unit is not None and reported.get("iv") and raw_iv is not None:
            v = float(raw_iv)
            v = v / 100.0 if unit == "percent" else v
            if math.isfinite(v) and gex.iv_ok(v):
                iv = v
        settlement = "AM" if occ.root in INDEX_AM_ROOTS else "PM"
        out.append(Contract(
            symbol=name, root=occ.root, expiry=occ.expiry,
            settlement=settlement, strike=occ.strike,
            type=occ.type, multiplier=100, oi=oi, iv=iv,
            oi_source="cboe_csv", iv_source="cboe_csv" if iv is not None else None,
            oi_date=None, quote_ts=None, iv_ts=None,
        ))
    return out


def _report(expiry: date, name: str, prepared: list[Contract],
            spot: float, target: str, status_hint: str) -> dict:
    chosen = [c for c in prepared if c.expiry == expiry]
    valid = [c for c in chosen if c.valid and c.oi is not None and c.oi > 0]
    basic = {
        "mode": name, "expiry": expiry.isoformat(), "status": "INSUFFICIENTE",
        "reason": "", "source": GEX_SOURCE, "quality_certified": False,
        "call_wall": None, "put_wall": None, "flip": None, "regime": None,
        "net_gex": None, "gross_gex": None,
        "call_gex": None, "put_gex": None, "rows": [], "curve": [],
        "contracts": len(chosen), "valid": len(valid),
        "quality_ratio": 0.0, "gex_coverage": None,
    }
    if not chosen:
        basic["reason"] = f"Scadenza {expiry:%d/%m/%Y} assente dal CSV, nessun livello ipotizzato."
        return basic
    if not any(c.type == "call" for c in chosen) or not any(c.type == "put" for c in chosen):
        basic["reason"] = "Una delle due componenti Call/Put manca."
        return basic
    cov = gex.coverage(chosen, spot)
    gcov = gex.gex_cov(chosen, spot)
    basic["quality_ratio"] = cov.ratio
    basic["gex_coverage"] = gcov.ratio
    distinct = len({c.strike for c in valid})
    valid_call = sum(c.type == "call" for c in valid)
    valid_put = sum(c.type == "put" for c in valid)
    # Non richiediamo "data OI verificata" per un mero modello diagnostico.
    # Le catture certificate Alpaca/Edge adottano una gate ulteriore OI-age,
    # deliberatamente NON certificata dal CSV.
    eligible = (
        cov.eligible >= 20 and cov.ratio >= .95
        and gcov.ratio is not None and gcov.ratio >= .98
        and distinct >= 20 and valid_call >= 10 and valid_put >= 10
    )
    if not eligible:
        basic["reason"] = (
            f"Copertura insufficiente: {cov.valid}/{cov.eligible} contratti, "
            f"GEX ±5% {gcov.pct if gcov.pct is not None else 'N/D'}%, "
            f"strike distinti validi {distinct}, Call {valid_call}, Put {valid_put}. "
            "Soglie diagnostiche: contratti ≥95%, GEX ≥98%."
        )
        return basic
    levels, _, _ = gex.compute_levels(target, chosen, spot)
    curve = gex.profile_curve(chosen, spot, points=201)
    rows = gex.strike_rows(chosen, spot * .90, spot * 1.10)
    net = math.fsum(c.gex for c in valid)
    gross = math.fsum(abs(c.gex) for c in valid)
    calls = math.fsum(c.gex for c in valid if c.type == "call")
    puts = math.fsum(c.gex for c in valid if c.type == "put")
    if not math.isclose(net, calls + puts, rel_tol=1e-9, abs_tol=.01):
        basic["reason"] = "Riconciliazione NET GEX Call+Put fallita."
        return basic
    basic.update({
        "status": "DIAGNOSTICO", "reason": status_hint,
        "call_wall": levels.call_wall, "put_wall": levels.put_wall,
        "flip": levels.nearest_zero_gamma, "regime": levels.regime,
        "net_gex": net, "gross_gex": gross,
        "call_gex": calls, "put_gex": puts,
        "rows": rows, "curve": curve,
    })
    return basic


def analyze_csv_gex(blob: bytes, symbol: str, iv_mode="auto") -> dict:
    """Analizza SOLO il CSV caricato; calcoli locali senza servizi o dati esterni."""
    if symbol is None or not isinstance(symbol, str):
        raise ValueError("Ticker CSV mancante.")
    doc = csv_to_snapshot(blob, symbol)
    provenance = doc.get("_import_provenance") or {}
    if provenance.get("source") != GEX_SOURCE or provenance.get("timestamp_utc_converted") is not True:
        raise ValueError("Non e' un CSV originale con timestamp sorgente verificato.")
    captured = datetime.strptime(
        doc["timestamp"], "%Y-%m-%d %H:%M:%S"
    ).replace(tzinfo=UTC)
    if captured > datetime.now(UTC) + timedelta(minutes=5):
        raise ValueError("CSV con data futura: fotografia non verificabile.")
    spot = float(doc["data"]["current_price"])
    if not math.isfinite(spot) or spot <= 0:
        raise ValueError("Prezzo Cboe mancante o non valido.")
    accepted = {str(o["option"]) for o in doc["data"]["options"]}
    presence = _raw_field_presence(blob, accepted)
    unit, unit_note = _iv_normalization(doc["data"]["options"], presence, iv_mode)
    contract_list = _from_snapshot(doc, presence, unit)
    cal = _calendar(captured)
    target = _target_expiries(captured, cal)
    prepared = gex.finalize(contract_list, spot, captured, cal)
    reports = {}
    for name, expiry in target.items():
        reports[name] = _report(
            expiry, name, prepared, spot, symbol,
            "OI del CSV senza data certificata; IV/quotazioni non sincronizzate "
            "con feed Alpaca. Risultato NON certificato, solo studio.",
        )
    if unit is None:
        for report in reports.values():
            report.update(
                status="INSUFFICIENTE", reason=unit_note, call_wall=None,
                put_wall=None, flip=None, regime=None,
                net_gex=None, gross_gex=None, call_gex=None, put_gex=None,
                curve=[], rows=[],
            )
    return {
        "source": GEX_SOURCE,
        "model": MODEL_LABEL,
        "symbol": symbol,
        "sha256": hashlib.sha256(blob).hexdigest(),
        "timestamp_utc": captured.isoformat(),
        "timestamp_rome": captured.astimezone(ROME).strftime("%d/%m/%Y %H:%M:%S"),
        "spot": spot, "iv_unit": unit, "iv_note": unit_note,
        "csv_contracts": len(contract_list), "oi_missing": sum(
            not presence.get(c.symbol, {}).get("oi") for c in contract_list
        ),
        "iv_missing": sum(
            not presence.get(c.symbol, {}).get("iv") for c in contract_list
        ),
        "reports": reports,
        "quality_certified": False,
    }
