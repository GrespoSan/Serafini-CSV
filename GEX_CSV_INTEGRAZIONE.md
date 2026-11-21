# GEX Edge-style autonomo — Serafini · Analisi CSV

## Architettura e provenienza

Questo modulo **non** legge dall'app Serafini SPX, non usa Supabase, non usa servizi attivi del laboratorio Edge e **non** effettua nuove chiamate Alpaca/OCC. Accetta solo la fotografia CSV Cboe caricata nella stessa sessione Streamlit. Il NET GAMMA originale non è alterato.

Il calcolo matematico proviene dal motore testato in GrespoSan/SPX-Edge-GEX-Lab:
- gexlab/engine/gex.py (blob 156713de1d593fb8ea38e3a7a8aae2ad5a1a361d)
- gexlab/engine/bsm.py (blob 88e59096ecece2d4b98beab464cef35500f125b9)
- gexlab/engine/calendar.py (blob 1d86cbff0e7481716b07e57fd6b8a3ebf28d1fe0)
- gexlab/models.py (blob b60e5bb6c392212871dfad678b993f94b45ad253)

Sono incorporati **solo i moduli matematici puri**, con import locali in csv_gex_core. Restano fuori credenziali, client REST, cache condivise, storage, scheduler e comandi di trading. Non è richiesto aprire l'altra app.

## Modello e unità

- Gamma BSM da spot, strike, IV e tempo a settlement, r=q=0
- GEX contratto = Gamma BSM × Open Interest × 100 × Spot² × 0,01, Call positiva / Put negativa (ipotesi su posizioni dealer **non osservate**)
- NET GEX = somma dei contributi Call e Put, USD per movimento del sottostante dell'1%
- Call Wall = strike con maggior Call GEX; Put Wall = maggior |Put GEX| nella fascia ±10%
- Gamma Flip = zero-crossing della curva entro ±10% spot; se assente resta N/D
- Regime: soglia neutra pari al 2% del GEX lordo, come motore Edge
- Scenario teorico = 201 prezzi tra −10% e +10% con OI, IV e T congelati

Non sono i calcoli NET GAMMA Serafini **(OI + Volume) × Gamma Call − (OI + Volume) × Gamma Put**.

## Dati dal CSV e limiti

Disponibili nel file importabile: ticker e codici OCC, strike, timestamp con fuso esplicito, spot/precedente, Call/Put, OI, Volume, Gamma Cboe; quando esportati, IV, Delta, Bid, Ask.

Non verificabili dal CSV: data OI del singolo contratto, origine e latenza delle singole quote Alpaca, allineamento temporale IV/spot, stato OPRA vs indicative, posizioni dealer reali. **La qualità certificata rimane sempre falsa.**

Per la visualizzazione diagnostica richiediamo almeno 20 contratti eleggibili, copertura valida almeno 95%, GEX misurabile almeno 98% nella banda ±5%, almeno 20 strike distinti validi, almeno 10 Call e 10 Put validi. In caso contrario tutti i livelli GEX sono N/D; nessun fallback a zero, interpolazione di strike o Gamma Cboe. I valori IV ambigui richiedono selezione esplicita dell'unità. OI vuoti sono trattati come mancanti, non come zero.

Il calendario XNYS è un **proxy di sessione**, non il settlement ufficiale OCC; le radici indice standard sono interpretate AM e le settimanali PM. In assenza di scadenze realmente nel CSV non generiamo livelli.

## Interfaccia

1. In **ANALISI NET GAMMA**, selezionare mercato e caricare il CSV originale.
2. Aprire **ANALISI GEX · Edge-style da CSV — modulo indipendente**.
3. Confermare le unità IV se non riconoscibili in modo univoco e premere **Calcola GEX dalla fotografia CSV**.
4. Selezionare 0DTE oppure Weekly. Con qualità insufficiente la schermata mostra N/D.

L'elaborazione non parte in automatico quando l'expander è chiuso. Il risultato è riutilizzato per lo stesso SHA256, simbolo e formato IV; cambiando file non si mostra il vecchio risultato.

## Test e gestione futura

Workflow: .github/workflows/csv-gex-tests.yml. Test: tests/test_csv_gex_integration.py. Comprende golden Gamma/GEX, indipendenza 0DTE/Weekly, IV/OI mancanti e IV ambiguo, no-lookahead e fonte. Include il test preesistente del filtro radici Azioni.

Un GEX **veramente alimentato da Alpaca/OPRA con OI OCC datato** richiederà un adattatore di acquisizione aggiuntivo, credenziali nel solo Streamlit Secrets, controlli per quote, età dell'OI, calendario e copertura (gate 1.3). Questo adattatore **non** è presente in questa versione e non va confuso con il motore diagnostico CSV.
