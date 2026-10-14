# components/heatmap.py
import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from data.datos import (
    MESES, HEATMAP_COLORSCALE,
    CARD_BG, TEXT_MAIN, TEXT_MUTED, COLOR_PRIMARY_DEEP,
)


def render_heatmap(anio: str, datos):
    """Renderiza el heatmap de estacionalidad: mes x tipo, con columna Total.

    `datos` expone TIPOS y get_heatmap(anio) (data.datos para el dataset de
    ejemplo, o un data.procesar.DatosBundle para datos subidos).
    """
    mt = datos.get_heatmap(anio)
    totales_fila = [sum(fila) for fila in mt]
    # Etiqueta legible: el nombre del tipo (si el dataset solo trae codigos como "01" o "10", se ven
    # los nombres y no numeros sueltos). Los nombres largos se recortan para que entren a la izquierda.
    tipo_desc = getattr(datos, "TIPO_DESC", {}) or {}

    def _etiqueta(t):
        d = str(tipo_desc.get(t, t))
        return d if len(d) <= 24 else d[:23] + "…"

    y_labels = [_etiqueta(t) for t in datos.TIPOS]
    if len(set(y_labels)) < len(y_labels):          # nombres repetidos: se agrega el codigo
        y_labels = [f"{l} ({t})" for l, t in zip(y_labels, datos.TIPOS)]

    # Dos subplots con ancho fijo (12 meses + columna Total) en vez de dos
    # trazas de Heatmap sobre el mismo eje categorico: con trazas separadas
    # sobre un eje compartido, Plotly no reparte el ancho de celda de forma
    # pareja y la columna Total termina renderizando como una tira angosta.
    fig = make_subplots(
        rows=1, cols=2,
        column_widths=[0.90, 0.10],
        horizontal_spacing=0.015,
        shared_yaxes=True,
    )

    # Heatmap principal (12 meses). textfont.color de go.Heatmap solo admite
    # un color unico (no por celda), por eso usamos un texto oscuro fijo que
    # se lee bien en toda la escala clara del gradiente.
    fig.add_trace(go.Heatmap(
        z=mt,
        x=MESES,
        y=y_labels,
        colorscale=HEATMAP_COLORSCALE,
        showscale=False,
        text=mt,
        texttemplate="%{text}",
        textfont={"size": 10, "color": TEXT_MAIN},
        hovertemplate="<b>%{y}</b><br>%{x}: %{z} expedientes<extra></extra>",
        xgap=2,
        ygap=2,
    ), row=1, col=1)

    # Columna "Total" con color fijo (acento principal), en su propio subplot
    z_total = [[t] for t in totales_fila]
    fig.add_trace(go.Heatmap(
        z=z_total,
        x=["Total"],
        y=y_labels,
        colorscale=[[0, COLOR_PRIMARY_DEEP], [1, COLOR_PRIMARY_DEEP]],
        showscale=False,
        text=z_total,
        texttemplate="%{text}",
        textfont={"size": 10, "color": "#ffffff"},
        hovertemplate="<b>%{y}</b><br>Total anual: %{z}<extra></extra>",
        xgap=2,
        ygap=2,
        zmin=0, zmax=1,
    ), row=1, col=2)

    # type="category": sin esto, si los tipos parecen numeros Plotly arma un eje numerico y las filas se
    # desalinean (filas de distinto alto, etiquetas 2 y 4 sueltas).
    fig.update_yaxes(type="category", autorange="reversed", row=1, col=1)  # el más frecuente arriba
    fig.update_yaxes(type="category", autorange="reversed", showticklabels=False, row=1, col=2)

    fig.update_layout(
        title=dict(
            text="ESTACIONALIDAD - RECLAMOS POR MES Y TIPO",
            font=dict(size=12, color=TEXT_MUTED),
            x=0,
        ),
        plot_bgcolor=CARD_BG,
        paper_bgcolor=CARD_BG,
        font=dict(color=TEXT_MAIN),
        height=220,
        margin=dict(l=min(10 + 7 * max(len(l) for l in y_labels), 190), r=20, t=40, b=40),
        showlegend=False,
    )

    st.plotly_chart(fig, width='stretch')
    st.caption("Color intenso = total anual por tipo")
