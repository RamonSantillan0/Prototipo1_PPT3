# components/kpi.py
import html

import streamlit as st


def render_kpi(anio: str, datos):
    """Renderiza la fila de KPI: total general (separado) + top 3 tipos de reclamo.

    `datos` es cualquier objeto con la interfaz de data.datos: TOTALES,
    ANIO_ANTERIOR, TIPOS, TIPO_DESC, TIPOS_N (el modulo data.datos para el
    dataset de ejemplo, o un data.procesar.DatosBundle para datos subidos).
    """
    total = datos.TOTALES[anio]
    prev = datos.ANIO_ANTERIOR[anio]
    tipos_n = datos.TIPOS_N[anio]
    tipos = datos.TIPOS
    tipo_desc = datos.TIPO_DESC

    delta_str = None
    if prev:
        pct = round((total - prev) / prev * 100)
        delta_str = f"{pct:+d}% vs año anterior"

    # Dos grupos claramente separados: el total general (1 columna, con acento)
    # y el Top 3 de tipos de reclamo (3 columnas agrupadas bajo su propia etiqueta).
    col_total, col_top3 = st.columns([1, 3], gap="medium")

    with col_total:
        with st.container(key="kpi_total"):
            st.markdown('<div class="section-title">General</div>', unsafe_allow_html=True)
            st.metric(
                label="Total expedientes",
                value=f"{total:,}".replace(",", "."),
                delta=delta_str,
            )

    with col_top3:
        with st.container(key="kpi_top3"):
            st.markdown('<div class="section-title">Top 3 tipos de reclamo</div>', unsafe_allow_html=True)
            # Top 3 real: los tipos ordenados por cantidad en el año elegido
            orden = sorted(range(len(tipos)), key=lambda k: -tipos_n[k])[:3]
            cols = st.columns(len(orden))
            for i, col in zip(orden, cols):
                n = tipos_n[i]
                pct = round(n / total * 100) if total else 0
                codigo = str(tipos[i])
                nombre = str(tipo_desc.get(tipos[i], tipos[i]))
                # Tarjeta propia en vez de st.metric: el nombre completo se ve entero (en varias
                # lineas si hace falta) y la cifra queda chica, sin cortarse con "...".
                n_txt = f"{n:,}".replace(",", ".")
                sub = f'<span class="kpi-cod">{html.escape(codigo)}</span>' if codigo != nombre else ""
                with col:
                    st.markdown(
                        f'<div class="kpi-tipo">'
                        f'<div class="kpi-nombre" title="{html.escape(nombre)}">{html.escape(nombre)}</div>'
                        f'<div class="kpi-valor">{n_txt} {sub}</div>'
                        f'<span class="kpi-pct">{pct}% del total</span>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )

    st.markdown("")  # separador visual
