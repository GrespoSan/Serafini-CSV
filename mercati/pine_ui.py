"""Pannello Pine condiviso per i mercati della app Analisi CSV."""
import streamlit as st


def render_pine_controls(market: str, code: str, filename: str, key: str):
    """Download e copia usano ESATTAMENTE lo stesso script gia' generato."""
    if not code or not code.startswith("//@version=6"):
        raise ValueError("Codice Pine v6 assente o incompleto.")
    download_col, copy_col = st.columns(2, gap="small")
    with download_col:
        st.download_button(
            f"Scarica Pine {market} · fotografia corrente",
            data=code, file_name=filename, mime="text/plain",
            key=f"pine_download_{key}", on_click="ignore",
        )
    with copy_col:
        with st.container(key=f"pine_copy_{key}"):
            with st.expander("Visualizza e copia codice Pine", expanded=False):
                st.caption("Usa l'icona Copia per incollare il sorgente in TradingView.")
                st.code(code, language=None, wrap_lines=False)
