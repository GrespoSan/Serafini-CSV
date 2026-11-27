"""Regressioni UI NET GAMMA: testo compatto, dati invariati.

Controlli statici offline, senza richiedere Cboe, Yahoo, Massive o Streamlit Cloud.
Il motore e i suoi output sono verificati dalle suite numeriche esistenti.
"""
from pathlib import Path
import ast
import unittest

ROOT = Path(__file__).resolve().parents[1]


class NetGammaCompactUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.gamma = (ROOT / "gamma_section.py").read_text(encoding="utf-8")
        cls.app = (ROOT / "app.py").read_text(encoding="utf-8")

    def test_compact_ui_keeps_persistent_technical_notes_collapsed(self):
        s = self.gamma
        panel = 'with st.expander("Dettagli tecnici NET GAMMA · fonti e metodo", expanded=False):'
        self.assertIn(panel, s)
        self.assertEqual(s.count(panel), 1)
        self.assertIn("technical_notes = []", s)
        self.assertIn("for note in technical_notes:", s)
        self.assertGreaterEqual(s.count("technical_notes.append("), 15)
        self.assertLess(s.index('st.plotly_chart(fig, width="stretch"'),
                        s.index(panel))
        self.assertLess(s.index(panel), s.index("render_optional_compare("))
        self.assertLess(s.index(panel),
                        s.index("COME LEGGERE E USARE IL NET GAMMA SERAFINI"))
        self.assertIn("**Differenziale automatico.**", s)
        self.assertIn("**Estensione grafica:**", s)
        self.assertIn("**Totali originali Serafini:**", s)
        self.assertIn("**Formula e tooltip:**", s)
        self.assertIn("**StdDev Serafini v1.4:**", s)

    def test_essential_labels_and_warnings_remain_immediately_visible(self):
        s = self.gamma
        for phrase in (
            "NET GAMMA · Call − Put · 25+25",
            "GAMMA CALL (+) · 25+25",
            "GAMMA PUT (−) · 25+25",
            "**Scadenze:** 0DTE",
            "**Scadenza opzioni:**",
            "RILEVAMENTO",
            "Fotografia CSV Cboe · ore",
            "Prezzo ES",
            "**Solo Weekly disponibile nella fotografia.**",
            "**Pine disponibile — SOLO WEEKLY.**",
            "Pine NET GAMMA non disponibile:",
            "copertura strike incompleta.",
            "Nessun contratto trovato per questa scadenza",
            "0DTE del {day:%d/%m/%Y} assente nel CSV",
            "Ricalcolo non disponibile:",
            "Diagnostica fonti prezzo ES",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, s)
        self.assertRegex(s, r"value=False,\s*key='gamma_independent_scale_v1'")
        self.assertIn("if not covered:", s)
        self.assertIn("if omitted:", s)
        self.assertIn("with st.expander('Visualizza e copia codice Pine'", s)

    def test_math_scale_and_pine_workflows_unchanged(self):
        s = self.gamma
        for token in (
            "computed_profiles[title] = profile(snap, expiry, ref)",
            "max_strikes=200, buffer_pct=fallback_buffer,",
            "computed_profiles.values(), require_core=True",
            "shared_bounds = profile_gamma_bounds(visual_profiles.values())",
            "gamma_component_totals(",
            "show_percent_lines = st.checkbox(",
            "show_visual_extension = st.checkbox(",
            "value=True, key='gamma_visual_extension_v1'",
            "value=False, key=\"gamma_percent_lines_v1\"",
            "add_es_quote_to_net_gamma(",
            "make_pine_weekly_only(",
            "script = make_pine(",
            "prepare_pine_with_csv_gex(",
        ):
            with self.subTest(token=token):
                self.assertIn(token, s)

    def test_prior_verbose_text_no_longer_main_body(self):
        s = self.gamma
        self.assertNotIn("st.caption('Tooltip:", s)
        self.assertNotIn("st.info('Venerdì: il profilo 0DTE", s)
        self.assertNotIn("st.caption(f'Estensione intelligente: i 50", s)
        self.assertIn("**Scadenze:** 0DTE", s)
        self.assertIn("Venerdì: 0DTE odierna · Weekly venerdì successivo.", s)
        self.assertIn("**{len(result['rows'])} strike originali (25+25)**", s)

    def test_mt4_note_moves_to_button_tooltip_without_action_change(self):
        app = self.app
        self.assertNotIn('st.caption("MT4: 100 strike', app)
        self.assertIn('"INVIA A MT4", type="primary", key="csv_mt4_send"', app)
        self.assertIn("help=\"Invia 100 strike reali per scadenza (50+50). \"", app)
        self.assertIn("payload = build_feed(", app)
        self.assertIn("publish(target, payload, role)", app)

    def test_sources_remain_syntactically_valid(self):
        ast.parse(self.gamma)
        ast.parse(self.app)


if __name__ == "__main__":
    unittest.main()
