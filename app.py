from datetime import datetime
from zoneinfo import ZoneInfo
from html import escape
import streamlit as st
import hmac
import hashlib

st.set_page_config(page_title="Serafini · Analisi CSV", page_icon="📊", layout="wide")

def verifica_password():
    inserita = st.session_state.pop("password_input", "")
    from mt4_manual import login_role
    configurata = st.secrets["APP_PASSWORD"]
    role = login_role(inserita, configurata, st.secrets.get("ADMIN_PASSWORD"))
    st.session_state.accesso = role is not None
    st.session_state.role = role

def esci():
    st.session_state.clear()

try:
    password_configurata = st.secrets.get("APP_PASSWORD")
except FileNotFoundError:
    password_configurata = None
if not isinstance(password_configurata, str) or not password_configurata.strip():
    st.error("Configura APP_PASSWORD nei Secrets di Streamlit per abilitare l’accesso.")
    st.stop()
if not st.session_state.get("accesso"):
    st.title("Serafini · Accesso")
    with st.form("login"):
        st.text_input("Password", type="password", key="password_input")
        st.form_submit_button("Accedi", on_click=verifica_password)
    if st.session_state.get("accesso") is False:
        st.error("Password errata.")
    st.stop()
# Sessions created before the role upgrade remain read-only until a new login.
role = st.session_state.get("role", "friend")
from mt4_manual import admin_enabled
if not admin_enabled(st.secrets.get("APP_PASSWORD"), st.secrets.get("ADMIN_PASSWORD")):
    role = "friend"
st.sidebar.caption("Accesso: " + ("Amministratore" if role == "admin" else "Lettore"))
st.sidebar.button("Esci", on_click=esci)
from csv_market import MARKETS, render_market, ticker_azione_da_csv
from offline_snapshot import load_local_snapshot, InvalidLocalSnapshot
from cboe_csv_import import InvalidCboeCSV, csv_coverage_warning
from gamma_section import render
from spx_massive_day_cache import purge_expired
try:
    if purge_expired():
        from daily_volatility import _fetch_massive_es
        _fetch_massive_es.clear()
except OSError:
    pass

st.title("Serafini · Analisi CSV")
st.markdown("""
<style>
[data-testid="stMainBlockContainer"],
[data-testid="stAppViewContainer"] .block-container {
    max-width: none !important;
    width: 100% !important;
    box-sizing: border-box;
    padding-left: clamp(1rem, 2vw, 3rem);
    padding-right: clamp(1rem, 2vw, 3rem);
}
/* Colora solo l'etichetta e il valore del selettore mercati. */
.st-key-mercato_selector label p,
.st-key-mercato_selector [data-baseweb="select"] > div,
.st-key-mercato_selector [data-baseweb="select"] span {
    color: #55d5f6 !important;
    font-weight: 700 !important;
}
/* Evidenzia in rosso i due controlli Pine, senza modificare altri pulsanti. */
.st-key-pine_download_control button,
.st-key-pine_download_control button p,
.st-key-pine_download_control button span {
    color: #ff626b !important;
    font-weight: 750 !important;
}
.st-key-pine_copy_container [data-testid="stExpander"] summary,
.st-key-pine_copy_container [data-testid="stExpander"] summary p,
.st-key-pine_copy_container [data-testid="stExpander"] summary span {
    color: #ff626b !important;
    font-weight: 750 !important;
}
/* Gli stessi comandi Pine sono condivisi fra NDX, Russell, Dow, GLD, USO e Azioni. */
[class*="st-key-pine_download_"] button,
[class*="st-key-pine_download_"] button p,
[class*="st-key-pine_download_"] button span,
[class*="st-key-pine_copy_"] [data-testid="stExpander"] summary,
[class*="st-key-pine_copy_"] [data-testid="stExpander"] summary p,
[class*="st-key-pine_copy_"] [data-testid="stExpander"] summary span {
    color: #ff626b !important;
    font-weight: 750 !important;
}
</style>
""", unsafe_allow_html=True)


asia_panel = None
photo_day = None
upload = None
store = None
# L'export GEX Pine non puo' riusare report di un file caricato in precedenza.
st.session_state['csv_gex_current_source'] = None
with st.expander("ANALISI NET GAMMA", expanded=True):
    st.header("NET GAMMA · formula Serafini")
    market = st.selectbox("Mercato", list(MARKETS), key="mercato_selector")
    equity = market == "Azioni"
    symbol = MARKETS[market]
    if symbol in ("SPX", "NDX", "RUT", "DJX", "GLD", "USO"):
        st.markdown(
            f"### Fotografia opzioni Cboe · {symbol} · "
            f"[↗ Apri Cboe](https://www.cboe.com/data/quotes/{symbol}/options)"
        )
    else:
        st.markdown(
            "### Fotografia opzioni Cboe · Azioni · "
            "[↗ Apri Cboe (NVDA)](https://www.cboe.com/data/quotes/NVDA/options)"
        )
    upload = st.file_uploader("Carica il CSV della catena opzioni Cboe", type=["csv"], key=f"csv_{market}")
    if upload is not None:
        try:
            if equity:
                symbol = ticker_azione_da_csv(upload.getvalue())
                st.caption(f"Titolo individuato automaticamente dal CSV Cboe: **{symbol}**")
            # Il GEX usa lo STESSO CSV del NET GAMMA, in automatico.
            # Si esegue prima della costruzione del Pine, con cache per file/IV.
            # Qualsiasi errore GEX non blocca il NET GAMMA Serafini.
            csv_bytes = upload.getvalue()
            csv_sha256 = hashlib.sha256(csv_bytes).hexdigest()
            # La visualizzazione GEX non deve mai essere una dipendenza
            # necessaria per caricare NET GAMMA, grafici o Pine originale.
            st.session_state['csv_gex_current_source'] = {
                'sha256': csv_sha256, 'symbol': symbol, 'oi_mode': 'auto',
            }
            st.session_state['csv_gex_last_report'] = None
            st.session_state['csv_gex_last_error'] = None
            try:
                # I servizi dati GEX sono separati da csv_gex_panel (solo UI).
                # Proteggere anche gli import: un errore GEX deve lasciare
                # il resto dell'app CSV perfettamente utilizzabile.
                from csv_gex_services import (
                    _cached_gex, _cached_occ, OI_LABELS, DEFAULT_OI_LABEL,
                )
                from csv_gex_pine import MODE_BY_LABEL
                oi_label = st.session_state.get('csv_gex_oi_source', DEFAULT_OI_LABEL)
                oi_mode = OI_LABELS.get(oi_label, 'auto')
                st.session_state['csv_gex_current_source']['oi_mode'] = oi_mode
                iv_label = st.session_state.get(
                    'csv_gex_iv_units',
                    'Rilevamento automatico (blocco se IV ambigua)',
                )
                iv_mode = MODE_BY_LABEL.get(iv_label, 'auto')
                if oi_mode == "csv":
                    gex_report = _cached_gex(csv_bytes, symbol, iv_mode)
                else:
                    # Non associare OI OCC corrente a una foto CSV storica.
                    from datetime import timezone
                    from cboe_csv_import import csv_to_snapshot
                    from csv_gex_core.calendar import NY
                    from csv_gex_oi import OiSourceError
                    occ_values, occ_provenance, occ_error = None, None, None
                    try:
                        doc = csv_to_snapshot(csv_bytes, symbol)
                        stamp = datetime.strptime(
                            doc["timestamp"], "%Y-%m-%d %H:%M:%S"
                        ).replace(tzinfo=timezone.utc)
                        if stamp.astimezone(NY).date() != datetime.now(NY).date():
                            raise OiSourceError(
                                "CSV non della seduta odierna: OCC corrente "
                                "non è un dato storico equivalente."
                            )
                        accepted = tuple(sorted(
                            {str(item["option"]) for item in doc["data"]["options"]}
                        ))
                        occ_values, occ_provenance = _cached_occ(symbol, accepted)
                    except (OiSourceError, ValueError, KeyError,
                            RuntimeError, TimeoutError, OSError) as occ_exc:
                        occ_error = str(occ_exc)[:230]
                    gex_report = _cached_gex(
                        csv_bytes, symbol, iv_mode, oi_mode,
                        occ_values, occ_provenance, occ_error
                    )
                st.session_state['csv_gex_last_report'] = (
                    (csv_sha256, symbol, iv_mode, oi_mode), gex_report,
                )
            except Exception as exc:
                # Fallback controllato: il NET GAMMA NON dipende dal GEX.
                st.session_state['csv_gex_last_error'] = (
                    type(exc).__name__ + ': ' + str(exc)[:250]
                )
            if market == "SP500":
                store = load_local_snapshot(upload.name, upload.getvalue())
                warning = csv_coverage_warning(store.import_provenance)
                if warning:
                    st.warning(warning)
                week = store.week
                snaps = store.list(f"{week}/snapshots/")
                st.session_state[f"serafini_selected_snapshot_{week}"] = store.filename
                asia_panel = render(store, week, snaps, [], show_heading=False, selector_external=True)
                if role == "admin" and asia_panel:
                    st.caption("MT4: 100 strike reali per scadenza (50+50); il nucleo 25+25 resta invariato. Stesso feed manuale di SPX.")
                    if st.button("INVIA A MT4", type="primary", key="csv_mt4_send"):
                        try:
                            from mt4_manual import build_feed, publish, ManualStore
                            payload = build_feed(
                                asia_panel["snapshot"], asia_panel["reference_spx"],
                                asia_panel["es_spx_basis"], asia_panel["basis_info"],
                                st.session_state.get("csv_gex_current_source"),
                                st.session_state.get("csv_gex_last_report"),
                                st.session_state.get("csv_gex_iv_units", ""),
                            )
                            target = ManualStore(st.secrets.get("SUPABASE_URL"),
                                                 st.secrets.get("SUPABASE_SERVICE_ROLE_KEY"))
                            publish(target, payload, role)
                            st.success("CSV manuale pubblicato e verificato nel feed privato MT4.")
                            if b"gex_model," not in payload:
                                st.warning("NET GAMMA inviato; GEX N/D: fotografia o modello non validi per GEX.")
                        except Exception as exc:
                            st.error("Invio MT4 non riuscito: " +
                                     (str(exc) if isinstance(exc, ValueError) else type(exc).__name__))
            else:
                photo_day = render_market(upload, symbol, equity)
        except (InvalidLocalSnapshot, InvalidCboeCSV, ValueError) as exc:
            st.error(str(exc))

# Modulo rigorosamente isolato: usa solo il CSV caricato, nessun archivio remoto.
# Un'eventuale indisponibilita' del GEX non deve bloccare il NET GAMMA.
with st.expander("ANALISI GEX · Edge-style da CSV — modulo indipendente", expanded=False):
    try:
        from csv_gex_panel import render as render_csv_gex
        render_csv_gex(
            upload.getvalue() if upload is not None else None,
            symbol,
            es_spx_basis=(asia_panel.get('es_spx_basis')
                          if market == "SP500" and asia_panel is not None else None),
        )
    except Exception as exc:
        st.error("Modulo GEX separato non disponibile: " + type(exc).__name__ +
                 ". Le analisi NET GAMMA precedenti restano utilizzabili.")

# Calendario CASH USA indipendente dalla data del CSV caricato: quando
# l'expander è chiuso deve comunque evidenziare Thanksgiving/chiusure.
# Non viene usato per inferire prezzi, scadenze 0DTE o orari CME/Cboe.
from us_market_calendar import today_rome_market_status, NYSE_SOURCE, CBOE_SOURCE, CME_SOURCE
nyse_status = today_rome_market_status()
if nyse_status["status"] == "holiday":
    context_suffix = " · 🇺🇸 FESTIVITÀ USA — CASH CHIUSO"
elif nyse_status["status"] == "early_close":
    context_suffix = " · 🇺🇸 CHIUSURA ANTICIPATA CASH"
else:
    context_suffix = ""

with st.expander(
    "ANALISI DEL CONTESTO — News · Volatilità · Trend Daily" + context_suffix,
    expanded=False,
):
    if nyse_status["status"] in ("holiday", "early_close"):
        # Evidenzia SOLO il testo; nessun riquadro colorato o sfondo extra.
        # Il calendario mantiene le stesse fonti e lo stesso comportamento.
        st.markdown(
            '<div style="background:transparent;padding:5px 0 12px 0;">'
            '<div style="color:#ffcf70;font-size:1.12rem;'
            'font-weight:750;line-height:1.45;">'
            + escape(f"{nyse_status['title']} — {nyse_status['day']}")
            + '</div>'
            '<div style="color:#e5e7eb;font-size:1.00rem;'
            'line-height:1.55;margin-top:5px;">'
            + escape(nyse_status["detail"])
            + '</div></div>',
            unsafe_allow_html=True,
        )
        st.caption(
            "Calendario **mercato azionario cash USA** (non calendario "
            "futures/opzioni): "
            f"[NYSE]({NYSE_SOURCE}) · "
            f"[Cboe SPX]({CBOE_SOURCE}) · "
            f"[CME futures ES]({CME_SOURCE}). "
            "Verificare gli orari speciali dei singoli prodotti."
        )
    elif nyse_status["status"] == "weekend":
        st.info(
            f"**{nyse_status['title']} — {nyse_status['day']}**. "
            "Non determina automaticamente l'orario di negoziazione "
            "degli strumenti futures."
        )
    elif nyse_status["status"] == "unknown":
        st.info(nyse_status["detail"])
    iso = (photo_day or datetime.now(ZoneInfo("Europe/Rome")).date()).isocalendar()
    week_label = store.week if store else f"{iso.year}-W{iso.week:02d}"
    st.markdown(f"**Settimana ISO (AAAA-WNN)** · {week_label}")
    # L'analisi viene visualizzata automaticamente; il download Massive ES
    # viene gestito dalla cache condivisa giornaliera. Anche con expander
    # chiuso il codice esegue, ma i dati Massive già letti non si riscaricano.
    st.markdown('#### News e calendario macroeconomico')
    from macro_calendar import render as render_macro_calendar
    render_macro_calendar()
    st.divider()

    # Il quadro VX e il Daily usano le proprie fonti CBOE/Massive.
    # La data corrente italiana non dipende dalla presenza di snapshot
    # Supabase, dal numero di registri o dal file CBOE selezionato.
    from vix_regime import render as render_vix_context
    trend_day = datetime.now(ZoneInfo('Europe/Rome')).date()
    es_daily_context = None
    daily_error = None
    try:
        context_data = render_vix_context(trend_day, return_context=True)
        es_daily_context = context_data.get('previous_daily_range')
    except Exception:
        st.info('Il quadro volatilità VX non è disponibile per la giornata corrente.')
        # Il Trend Daily conserva la sua fonte Massive anche se la
        # lettura dei settlement CBOE fallisce.
        try:
            from daily_volatility import previous_es_daily_range
            es_daily_context = previous_es_daily_range(trend_day)
        except Exception:
            daily_error = 'Massive ES non disponibile: verificare Secrets e contratto.'
    st.divider()
    from trend_daily_section import render as render_trend_daily
    es_daily_context = es_daily_context or {}
    render_trend_daily(reference_day=trend_day,
                       daily_bars=es_daily_context.get('daily_bars'),
                       contract=es_daily_context.get('ticker'),
                       daily_error=daily_error,
                       modeled_gex=None)

    # Il Quadro è sempre visibile dopo il Trend Daily. Senza uno snapshot SPX
    # resta la lettura autonoma dell'Asia ES, senza inventare candidati C1/P1.
    st.divider()
    st.subheader("QUADRO OPERATIVO — ORE 09:00")
    from asia_gamma import render_auto as render_asia_gamma
    if asia_panel is not None:
        render_asia_gamma(
            asia_panel['day'], asia_panel['c1_es'], asia_panel['p1_es'],
            level_context=asia_panel['level_context'],
        )
    else:
        render_asia_gamma(trend_day, None, None)
