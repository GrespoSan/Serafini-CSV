"""Quotazione ES Yahoo condivisa da NET GAMMA e curva GEX.

Una sola cache breve per Streamlit: prezzo indicativo/differito, non modifica
mai lo snapshot Cboe, i livelli SPX, il basis ES-SPX o il Pine.
"""
import streamlit as st

from csv_gex_es_quote import fetch_es_quote


@st.cache_data(show_spinner=False, max_entries=5, ttl=60)
def cached_es_quote():
    """Ultimo prezzo ES verificato (max 90m); N/D se Yahoo non lo fornisce."""
    return fetch_es_quote()


# Nome preesistente, importabile da entrambi i pannelli.
_cached_es_quote = cached_es_quote
