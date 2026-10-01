"""Entidad · Sistema de Reclamos (prototipo): dashboard + consulta normativa (RAG) + recepción de reclamos.

Ejecutar:  streamlit run app.py
"""
import streamlit as st

st.set_page_config(
    page_title="Entidad · Sistema de Reclamos",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# CSS global - Estilo 4: Teal Profesional (fondo gris claro)
st.markdown("""<style>
.main { background-color: #EEF2F1; }
.block-container { padding-top: 2.5rem; padding-bottom: 1rem; }
div[data-testid="metric-container"] {
    background: #FAFCFB;
    border: 0.5px solid #DCE6E4;
    border-radius: 8px;
    padding: 0.75rem 1rem;
}
div[data-testid="metric-container"] label { color: #33504C !important; font-size: 14px !important; font-weight: 600; }
div[data-testid="metric-container"] div[data-testid="stMetricValue"] { color: #0B211E; font-size: 22px; }
div[data-testid="stMetricDelta"] { color: #33504C !important; }
h1, h2, h3 { color: #0B211E; }
.section-title {
    font-size: 14px; font-weight: 700; color: #33504C;
    text-transform: uppercase; letter-spacing: 0.04em; margin-bottom: 0.5rem;
}
[data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] p {
    color: #33504C !important;
}
.st-key-kpi_total {
    padding-right: 1.25rem;
    border-right: 1px solid #DCE6E4;
}
.st-key-kpi_total div[data-testid="metric-container"] {
    border-left: 3px solid #0D9488;
    background: #E6F5F3;
}
.kpi-tipo {
    background: #FAFCFB; border: 0.5px solid #DCE6E4; border-radius: 8px;
    padding: 0.6rem 0.85rem; height: 100%;
}
.kpi-nombre {
    font-size: 13px; font-weight: 600; color: #33504C; line-height: 1.25;
    white-space: normal; overflow-wrap: anywhere; min-height: 2.5em;
}
.kpi-valor { font-size: 22px; color: #0B211E; margin: 0.15rem 0 0.3rem; }
.kpi-cod { font-size: 12px; color: #33504C; background: #E6F5F3; border-radius: 4px; padding: 1px 6px; vertical-align: middle; }
.kpi-pct { font-size: 12px; color: #33504C; background: #E4EBE9; border-radius: 10px; padding: 2px 8px; }
.st-key-kpi_top3 div[data-testid="metric-container"] {
    background: #FAFCFB;
}
header[data-testid="stHeader"] {
    background: #EEF2F1;
    border-bottom: 1px solid #DCE6E4;
}

/* Sidebar: mismo tono que el fondo general */
section[data-testid="stSidebar"] {
    background-color: #E4EBE9;
    border-right: 1px solid #DCE6E4;
}
section[data-testid="stSidebar"] h1,
section[data-testid="stSidebar"] h2,
section[data-testid="stSidebar"] h3,
section[data-testid="stSidebar"] label,
section[data-testid="stSidebar"] p {
    color: #0B211E !important;
}
</style>""", unsafe_allow_html=True)

paginas = st.navigation([
    st.Page("paginas/dashboard.py", title="Dashboard", icon="📊", default=True),
    st.Page("paginas/consulta_normativa.py", title="Consulta normativa (RAG)", icon="📚", url_path="consulta"),
    st.Page("paginas/recepcion.py", title="Recepción de reclamos (chatbot)", icon="💬", url_path="recepcion"),
])
paginas.run()
