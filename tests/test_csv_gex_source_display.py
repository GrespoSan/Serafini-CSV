"""Regressione provenienza GEX: fonti effettive e orari (non feed Alpaca)."""
from pathlib import Path
import unittest

from csv_gex_source_display import describe_gex_sources, _occ_download_rome

ROOT = Path(__file__).resolve().parents[1]


def fixture(effective="OCC_SERIES_SEARCH", *, fallback=None):
    return {
        "source": "CBOE_CSV_MANUAL_USER_EXPORT",
        "timestamp_rome": "24/11/2026 16:02:00",
        "oi_info": {
            "requested_mode": "auto",
            "effective_source": effective,
            "occ_download_utc": ("2026-11-24T14:52:52.961664+00:00"
                                 if effective == "OCC_SERIES_SEARCH" else None),
            "fallback_reason": fallback,
            "oi_date_status": "OCC_NON_DICHIARA_DATA_OI_SERIE",
        },
    }


class GexProvenanceTests(unittest.TestCase):
    def test_occ_source_uses_two_distinct_rome_times_not_alpaca(self):
        result = describe_gex_sources(fixture())
        self.assertEqual(result["title"], "DATI GEX: CSV CBOE + OPEN INTEREST OCC")
        self.assertEqual(result["snapshot_clock"], "24/11/2026 16:02:00 Roma")
        self.assertEqual(result["oi_download_clock"], "24/11/2026 15:52:52 Roma")
        self.assertIn("OCC Series Search", result["oi_source"])
        self.assertIn("data di riferimento", result["oi_vintage"])
        self.assertIn("NON UTILIZZATA", result["alpaca"])
        self.assertIn("download, non l'aggiornamento", result["note"])

    def test_csv_only_does_not_display_occ_time_as_data_time(self):
        result = describe_gex_sources(fixture("CSV_CBOE"))
        self.assertEqual(result["title"], "DATI GEX: SOLO CSV CBOE")
        self.assertIn("Nessun download OCC", result["oi_download_clock"])
        self.assertIn("CSV Cboe", result["oi_source"])
        self.assertIn("data OI non documentata", result["oi_vintage"])

    def test_auto_fallback_display_uses_effective_not_requested(self):
        result = describe_gex_sources(
            fixture("CSV_CBOE", fallback="OCC non disponibile")
        )
        self.assertEqual(result["title"], "DATI GEX: SOLO CSV CBOE")
        self.assertNotIn("OCC Series Search", result["oi_source"])

    def test_occ_clock_dst_and_no_naive_timezone_assumptions(self):
        self.assertEqual(
            _occ_download_rome("2026-07-10T14:52:00Z"),
            "10/07/2026 16:52:00 Roma",
        )
        self.assertEqual(
            _occ_download_rome("2026-11-24T14:52:00+00:00"),
            "24/11/2026 15:52:00 Roma",
        )
        for bad in ("2026-11-24T14:52:00", "garbled"):
            self.assertIn("N/D", _occ_download_rome(bad))
        self.assertIn("N/D", _occ_download_rome(None))

    def test_unknown_oi_source_does_not_fall_back_silently(self):
        result = describe_gex_sources(fixture("UNRECOGNIZED"))
        self.assertIn("NON VERIFICATA", result["title"])
        self.assertIn("non verificata", result["oi_source"].lower())

    def test_only_ui_changed_no_modification_to_model_or_pine(self):
        panel = (ROOT / "csv_gex_panel.py").read_text(encoding="utf-8")
        self.assertIn("describe_gex_sources(info)", panel)
        self.assertIn("**Ora fotografia:**", panel)
        self.assertIn("**Ora download OCC:**", panel)
        self.assertIn("**Data reale OI:**", panel)
        self.assertIn("**Alpaca/OPRA:**", panel)
        self.assertNotIn("download {oi.get('occ_download_utc')", panel)
        self.assertIn("if oi.get(\"fallback_reason\"):", panel)


    def test_technical_details_are_collapsed_but_auditable(self):
        panel = (ROOT / "csv_gex_panel.py").read_text(encoding="utf-8")
        detail = 'with st.expander("Dettagli tecnici · fonti, qualità e metodo", expanded=False):'
        self.assertIn(detail, panel)
        before, behind = panel.split(detail, 1)
        self.assertIn("**Ora fotografia:**", before)
        self.assertIn("**Ora download OCC:**", before)
        self.assertIn("**Prezzi in ES/MES**", before)
        self.assertIn('if oi.get("fallback_reason"):', before)
        self.assertIn("**Identità CSV:**", behind)
        self.assertIn("**Data reale OI:**", behind)
        self.assertIn("**Modello:**", behind)
        self.assertIn("**Riconciliazione OCC:**", behind)
        self.assertIn("**SPX implicito dalle opzioni:", behind)
        self.assertIn('st.caption(info["iv_note"])', behind)
        self.assertIn('st.html(_gex_summary_card_html(', behind)
        self.assertNotIn('st.radio("Scadenza GEX"', behind)
        self.assertEqual(panel.count("**GEX modellato · diagnostico, non certificato.**"), 0)


if __name__ == "__main__":
    unittest.main()
