# Serafini · Analisi CSV

Su Streamlit Community Cloud usa app.py come file principale e Python 3.12. In Advanced settings → Secrets imposta APP_PASSWORD (stringa fra virgolette) e MASSIVE_API_KEY.

Per esecuzione locale estrai la cartella completa e configura APP_PASSWORD nel file .streamlit/secrets.toml. Su Windows con Python 3.12 avvia AVVIA.bat. Al primo avvio il programma installa le dipendenze. Su altri sistemi installa requirements.txt e avvia `streamlit run app.py`.

Per usare le sezioni che richiedono Massive crea il file `.streamlit/secrets.toml` nella cartella estratta. Copia dalla configurazione SPX MASSIVE_API_KEY, con il valore tra virgolette. La scadenza ES viene selezionata automaticamente secondo la stessa regola trimestrale del Nasdaq. Le altre fonti di contesto e i prezzi Yahoo richiedono Internet.

Scegli il mercato e carica il CSV del Quotes Dashboard Cboe con intestazione Last, Change, Date e colonne Calls, Strike, Puts, Gamma, Open Interest e Volume. Per SPX usa Options Range = All. La data e l’orario della fotografia provengono dal file. Nel pannello Azioni inserisci il ticker del file.

La sezione Contesto segue la modalità CSV locale di SPX. Il contatore Registri vale zero. La scheda Edge GEX opzionale che dipende dall’archivio ufficiale non è disponibile in questa modalità. Per i grafici Gold e Petrolio il rapporto continuo usa le barre ETF/future Yahoo a 5 minuti sincronizzate, come nella vista grafica Multi Market. Il differenziale dei quattro indici è calcolato automaticamente. In caso di indisponibilità dei prezzi esterni verifica le informazioni riportate nel pannello.

Sorgenti di riferimento: Serafini-SPX-Dashboard (178c8ef) e Multi-Market-NET-GAMMA, ramo v2-spx (b91d969).
