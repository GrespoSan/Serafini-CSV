"""Calendario NYSE cash USA per il pannello CONTESTO.

Sorgente sessioni/chiusure anticipate: exchange_calendars XNYS, con
timezone reali America/New_York ed Europe/Rome.
ATTENZIONE: non è il calendario Globex CME né delle opzioni SPX/GTH Cboe.
Nessuna rete, nessun download e nessun impatto sui dati NET GAMMA/GEX.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import exchange_calendars as xcals
import pandas as pd


NEW_YORK = ZoneInfo("America/New_York")
ROME = ZoneInfo("Europe/Rome")
NYSE_SOURCE = "https://www.nyse.com/trade/hours-calendars"
CBOE_SOURCE = "https://www.cboe.com/about/hours/us-options/"
CME_SOURCE = "https://www.cmegroup.com/trading-hours.html"


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    first = date(year, month, 1)
    return first + timedelta(days=(weekday - first.weekday()) % 7 + 7 * (n - 1))


def _last_weekday(year: int, month: int, weekday: int) -> date:
    following_month = (date(year + 1, 1, 1) if month == 12
                       else date(year, month + 1, 1))
    last = following_month - timedelta(days=1)
    return last - timedelta(days=(last.weekday() - weekday) % 7)


def _easter(year: int) -> date:
    """Calendario gregoriano: solo per denominare Good Friday se XNYS chiuso."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = (h + l - 7 * m + 114) % 31 + 1
    return date(year, month, day)


def _observed_fixed(year: int, month: int, day: int) -> date:
    original = date(year, month, day)
    if original.weekday() == 5:  # Saturday
        return original - timedelta(days=1)
    if original.weekday() == 6:  # Sunday
        return original + timedelta(days=1)
    return original


def _holiday_name(day: date) -> str:
    """Nome descrittivo, ma SOLO il calendario XNYS decide se è chiuso."""
    y = day.year
    thanksgiving = _nth_weekday(y, 11, 3, 4)
    if day == thanksgiving:
        return "Thanksgiving"
    if day == _easter(y) - timedelta(days=2):
        return "Good Friday (Venerdì Santo)"
    if day == _nth_weekday(y, 1, 0, 3):
        return "Martin Luther King Jr. Day"
    if day == _nth_weekday(y, 2, 0, 3):
        return "Presidents’ Day"
    if day == _last_weekday(y, 5, 0):
        return "Memorial Day"
    if day == _nth_weekday(y, 9, 0, 1):
        return "Labor Day"
    for month, number, name in (
        (1, 1, "Capodanno"),
        (6, 19, "Juneteenth"),
        (7, 4, "Independence Day"),
        (12, 25, "Natale"),
    ):
        if day == date(y, month, number):
            return name
        if day == _observed_fixed(y, month, number):
            return name + " (osservato)"
    # Capodanno dell'anno successivo quando cade di domenica.
    if day == date(y, 12, 31) and date(y + 1, 1, 1).weekday() == 5:
        # NYSE non osserva sempre il venerdì per il Capodanno del sabato.
        # Non etichettarlo come Capodanno senza evidenza di chiusura XNYS.
        return "Chiusura straordinaria NYSE"
    return "Festività o chiusura straordinaria NYSE"


def nyse_day_status(day: date) -> dict:
    """Stato cash USA onesto: holiday, early_close, weekend, regular, unknown.

    I giorni cash chiusi non implicano ES/CME o SPX/Cboe GTH chiusi.
    Fallimento del calendario: UNKNOWN, mai apertura/chiusura inventata.
    """
    if not isinstance(day, date) or isinstance(day, datetime):
        raise TypeError("Richiesta una data civile Europe/Rome")
    base = {
        "day": day.isoformat(),
        "calendar": "NYSE/XNYS",
        "source": NYSE_SOURCE,
        "cash_only": True,
    }
    try:
        calendar = xcals.get_calendar("XNYS")
        session = pd.Timestamp(day)
        is_session = bool(calendar.is_session(session))
        if not is_session:
            if day.weekday() >= 5:
                return {
                    **base, "status": "weekend",
                    "title": "WEEKEND — MERCATO CASH USA CHIUSO",
                    "detail": "NYSE/Nasdaq cash non negoziano nel fine settimana.",
                }
            holiday = _holiday_name(day)
            return {
                **base, "status": "holiday",
                "title": f"FESTIVITÀ USA — {holiday.upper()}",
                "detail": (
                    f"{holiday}: mercato azionario USA (NYSE) chiuso nella "
                    "sessione regolare. La chiusura cash NON implica la "
                    "chiusura totale dei futures ES/CME o delle opzioni "
                    "SPX/Cboe durante eventuali sessioni estese."
                ),
                "holiday": holiday,
            }

        close_utc = calendar.session_close(session)
        close_ny = close_utc.tz_convert(NEW_YORK)
        close_rome = close_utc.tz_convert(ROME)
        if close_ny.time() < time(16, 0):
            return {
                **base, "status": "early_close",
                "title": "SEDUTA RIDOTTA — MERCATO CASH USA",
                "detail": (
                    "NYSE cash: chiusura anticipata alle "
                    f"{close_ny:%H:%M} New York / "
                    f"{close_rome:%H:%M} Roma. "
                    "Il calendario CME ES e quello Cboe SPX possono "
                    "prevedere orari diversi."
                ),
                "close_ny": close_ny.strftime("%H:%M"),
                "close_rome": close_rome.strftime("%H:%M"),
            }

        return {**base, "status": "regular",
                "title": "SESSIONE REGOLARE CASH USA", "detail": ""}
    except (ValueError, TypeError, KeyError, OverflowError) as exc:
        return {
            **base, "status": "unknown",
            "title": "CALENDARIO NYSE NON VERIFICABILE",
            "detail": (
                "Impossibile accertare gli orari del mercato cash USA "
                f"({type(exc).__name__}); verificare il calendario ufficiale."
            ),
        }


def today_rome_market_status() -> dict:
    return nyse_day_status(datetime.now(ROME).date())
