# GEX Edge-style autonomo — Serafini · Analisi CSV

## Architettura e provenienza

Questo modulo **non** legge dall'app Serafini SPX, non usa Supabase, non usa servizi attivi del laboratorio Edge e **non effettua chiamate Alpaca/OPRA**. La fotografia CSV Cboe caricata in Streamlit fornisce sempre prezzi, IV e contratti. Per il solo **Open Interest** si può utilizzare il CSV oppure effettuare una chiamata autonoma a **OCC Series Search**, in modalità Auto (con fallback esplicito) o OCC-only. Il NET GAMMA originale non è alterato.

Il calcolo matematico proviene dal motore testato in GrespoSan/SPX-Edge-GEX-Lab:
- gexlab/engine/gex.py (blob 156713de1d593fb8ea38e3a7a8aae2ad5a1a361d)
- gexlab/engine/bsm.py (blob 88e59096ecece2d4b98beab464cef35500f125b9)
- gexlab/engine/calendar.py (blob 1d86cbff0e7481716b07e57fd6b8a3ebf28d1fe0)
- gexlab/models.py (blob b60e5bb6c392212871dfad678b993f94b45ad253)

Sono incorporati **solo i moduli matematici puri**, con import locali in csv_gex_core. Restano fuori credenziali, client REST, cache condivise, storage, scheduler e comandi di trading. Non è richiesto aprire l'altra app.

## Orari e fonte effettiva del GEX

La UI presenta esplicitamente **DATI GEX: SOLO CSV CBOE** oppure
**DATI GEX: CSV CBOE + OPEN INTEREST OCC**, in base alla fonte
effettivamente usata, non alla semplice scelta del menu Auto.
Mostra due orari differenti, entrambi convertiti in **Europe/Rome**:

- **Ora fotografia CSV Cboe**: timestamp originale del prezzo, delle IV e
  della catena utilizzata nel GEX.
- **Ora download OCC**: acquisizione dell'Open Interest se usato.
  OCC Series Search non certifica nel report la data reale degli OI;
  non si deve confondere l'ora del download con il loro as-of.
  Se il GEX usa OI CSV, compare «Nessun download OCC utilizzato».

L'app **non utilizza feed Alpaca/OPRA**: Edge-style descrive la matematica
del modello, non la fonte dati. Una fotografia CSV e un download OCC della
stessa seduta non sono necessariamente temporalmente sincronizzati.
In modalità Auto, il fallback OCC → CSV rimane esplicitamente dichiarato.
Questa distinzione è applicata alla visualizzazione e **non cambia** GEX,
NET GAMMA né Pine.

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

La qualità diagnostica segue il gate Edge originale: servono almeno 20 contratti eleggibili, **copertura dell'esposizione GEX stimata almeno 98% nella banda ±5%, calcolata sul rapporto NON arrotondato**, almeno 20 strike distinti validi e almeno 10 Call + 10 Put validi. La copertura numerica di contratti al 95% è soltanto un **indicatore di completezza**, non un secondo gate: altrimenti, in una catena SPX con 360/387 contratti validi e GEX stimato quasi interamente coperto, si bloccherebbero erroneamente i livelli. Se la copertura GEX non è stimabile, il modello non passa. Non forziamo dati mancanti né inventiamo IV, strike, Gamma Flip o livelli; OI vuoti non sono trattati come zero.

Il calendario XNYS è un **proxy di sessione**, non il settlement ufficiale OCC; le radici indice standard sono interpretate AM e le settimanali PM. In assenza di scadenze realmente nel CSV non generiamo livelli.

## Interfaccia e calcolo automatico

1. In **ANALISI NET GAMMA**, scegliere il mercato e caricare un unico CSV Cboe.
2. Prima della generazione del Pine, l'app calcola automaticamente NET GAMMA
   e, separatamente, GEX dal medesimo file; il modello GEX usa una cache
   vincolata ai byte CSV, simbolo e unità IV.
3. **Scarica Pine** o **Visualizza e copia codice Pine** forniscono
   automaticamente il NET GAMMA e i livelli GEX diagnostici disponibili.
   Non ci sono più il pulsante Calcola GEX né il toggle prima dell'esportazione.
4. La sezione **ANALISI GEX** è solo un pannello di lettura di report,
   curva, scadenze e qualità, indipendente dalla sua apertura.
5. Il formato IV è rilevato automaticamente di default. Soltanto in caso
   di IV ambigua è possibile selezionare decimale o percentuale nella
   sezione GEX: il ricalcolo e il Pine si aggiornano al rerun senza pulsanti.

Se GEX è insufficiente o fallisce il calcolo, il NET GAMMA originale e
il suo Pine continuano a funzionare **senza alcun livello GEX inventato**.
Per 0DTE e Weekly i controlli di qualità sono indipendenti; il Pine
contiene i soli gruppi validi.

## Grafici GEX · curva e profilo per strike

Nel pannello **ANALISI GEX** sono visibili in sequenza due grafici principali,
senza expander intermedio:

1. **Curva teorica GEX**: scenario prezzo ±10% con IV, OI e tempo congelati.
   La legenda sopra il grafico identifica la curva azzurra, lo spot della
   fotografia, Call Wall, Put Wall, Gamma Flip e, quando effettivamente
   disponibile nella banda, il prezzo ES Yahoo ritardato. I riferimenti
   sono linee distinte: nessuna etichetta sovrapposta agli assi.
2. **GEX by Strike · Calls/Puts**: barre orizzontali specchiate,
   Put negativi **viola** a sinistra e Call positivi **verde** a destra,
   medesime unità mld USD / movimento dell'1% e asse verticale di prezzo.
   Call Wall, Put Wall, Gamma Flip e spot del CSV hanno linee orizzontali
   con cartellini sul lato destro. Per SPX sono convertiti in **prezzo ES
   equivalente** con il differenziale già verificato dal Pine.

Il grafico per strike è **sempre aperto** sotto la curva. Il selettore
**±2% (default), ±5%, ±10%, Tutti** limita solo gli strike visualizzati
rispetto allo spot **della fotografia** (non alla quotazione ES in tempo
reale). Non modifica la catena originale, GEX, Call/Put Wall, Flip,
regime, scenario, né l'export Pine. Se un livello cade fuori dalla finestra,
viene dichiarato, non spostato o inventato. L'ES Yahoo attuale rimane una
serie separata, con provenienza e orario, e non cambia i valori GEX
calcolati dal CSV storico.

Test: `tests/test_csv_gex_chart_layout.py` e
`tests/test_csv_gex_es_display.py`.

## Pine Script: GEX automatico nel NET GAMMA esistente

Il modulo **csv_gex_pine.py** aggiunge in fondo al Pine originale esclusivamente
i livelli GEX modellati che hanno superato i controlli. Il prefisso
del codice NET GAMMA e le sue formule non vengono modificati.
L'attivazione grafica delle scadenze avviene **solo nelle impostazioni
TradingView**: GEX 0DTE ON e Weekly OFF di default, modificabili.

Le nuove linee GEX sono verdi (Call Wall), rosse (Put Wall) e gialle
(Gamma Flip). 0DTE ha linea piena e Weekly tratteggiata.
Ogni linea è un livello **statico** della fotografia e non si aggiorna alle
candele future; la curva scenari resta nel modulo Streamlit.

Il codice viene aggiunto solo se coincidenti **SHA-256 del CSV, ticker e
unità IV**. Se la scadenza è incompleta, quel gruppo GEX resta N/D e
non entra nel Pine. Per esportare sui futures sono riutilizzati
esclusivamente i mapping già verificati dalle funzioni NET GAMMA:
ES=SPX+basis; NQ=NDX+basis; RTY=RUT+basis;
YM=DJX×100+basis; GC=GLD×ratio; CL=USO×ratio.
Senza conversione valida, i livelli restano in scala indice/ETF nei Pine
che già permettono quell'opzione. L'export non acquisisce nulla da Alpaca.

Test: **tests/test_csv_gex_pine.py** e **tests/test_csv_gex_automatic_flow.py**, compresi mismatch fonte/IV, assenza
Gamma Flip, scadenza mancante, rapporti di proiezione e integrità del
codice NET GAMMA. La verifica automatica non equivale a una compilazione
nel Pine Editor di TradingView.

## Copertura grafica SPX e limiti Pine

Il NET GAMMA SPX resta **25 strike sopra + 25 sotto la chiusura SPX**
per tutte le analisi originali Serafini e per C1/P1. L'opzione
**Estensione intelligente NET GAMMA** resta ON di default in Streamlit
e in TradingView, ma NON aggiunge strike quando il nucleo originale
copre già il range noto e il margine di sicurezza.

La fascia ex ante considera la chiusura precedente, lo spot del CSV
e, quando verificabili, **gli estremi delle ultime 3–5 sedute RTH M15
complete precedenti alla fotografia (preferibilmente 5)**. L'analisi
riutilizza il dataset Yahoo ES=F già scaricato per StdDev, ma valida
indipendentemente gli OHLC di ciascuna RTH (27 barre M15 con orari
Chicago, nessun buco). Anche quando i 350 close della StdDev non sono
verificabili, un range RTH può essere verificato a parte.
Gli estremi ES sono proiettati nella fascia SPX con il differenziale
ES-SPX corrente **solo per visualizzare gli strike**, non come serie
storica SPX certificata. La trasformazione non modifica NET GAMMA/GEX.

Quando il range recente è valido, il margine resta adattivo: massimo tra
0,25% del riferimento, due passi mediani degli strike e il 20%
dell'escursione dei prezzi già noti, con tetto dell'1% del riferimento.
Se i 50 strike coprono la fascia, grafico e Pine restano ESATTAMENTE sui
50 originali per scadenza.

**Fallback di sicurezza:** se il range M15 recente o il differenziale
ES-SPX non sono verificabili, l'app sceglie una fascia più ampia ±5%
rispetto a riferimento e spot del CSV (non viene falsamente presentata
come movimento effettivamente osservato). Riempie solo con veri strike
Cboe disponibili. L'app mostra in chiaro la copertura e l'obiettivo
convertiti in ES per il mercato SP500.

Il Pine non interroga né Yahoo né Cboe: l'estensione visibile su
TradingView dipende dai dati già inseriti nel Pine al momento del download.
Per sfruttare il nuovo range serve **scaricare nuovamente il Pine**
dopo aver ricaricato il CSV.

Quando non bastano, vengono aggiunti solo strike reali Cboe sul
lato scoperto (o su entrambi se necessario), fino a **200 strike per
scadenza** 0DTE/Weekly. Il calcolo principale NET GAMMA/C1/P1 resta
sempre sul nucleo 25+25. Non entrano prezzi successivi allo snapshot.

Se gli strike reali superano la capacità, il campionamento include il
nucleo 50, gli estremi reali della fascia, un numero limitato dei picchi
NET GAMMA più intensi e strike distribuiti per prezzo. Si segnala
l'eventuale esclusione; **non** si aggregano o interpolano valori.
Nel Pine 200+200 strike richiedono al massimo 400 segmenti, con
margine per le baselines, proiezioni e fino a sei linee GEX, entro il
limite di 500 linee TradingView.

Test dedicati: `tests/test_csv_gex_quality_gate.py` e
`tests/test_net_gamma_dynamic_extension.py` e `tests/test_serafini_recent_rth.py`.

## Test e gestione futura

Workflow: .github/workflows/csv-gex-tests.yml. Test: tests/test_csv_gex_integration.py. Comprende golden Gamma/GEX, indipendenza 0DTE/Weekly, IV/OI mancanti e IV ambiguo, no-lookahead e fonte. Include il test preesistente del filtro radici Azioni.

Un GEX **veramente alimentato da Alpaca/OPRA con OI OCC datato** richiederà un adattatore di acquisizione aggiuntivo, credenziali nel solo Streamlit Secrets, controlli per quote, età dell'OI, calendario e copertura (gate 1.3). Questo adattatore **non** è presente in questa versione e non va confuso con il motore diagnostico CSV.
