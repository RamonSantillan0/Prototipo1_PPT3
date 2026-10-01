# components/barras.py
import streamlit as st
import plotly.graph_objects as go
from data.datos import COLORES_TIPO, CARD_BG, TEXT_MAIN, TEXT_MUTED


def hex_to_rgba(hex_color: str, alpha: float) -> str:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


def render_barras(anio: str, datos):
    """Renderiza barras agrupadas apiladas: localidad x tipo x canal de ingreso.

    `datos` expone TIPOS, TIPO_DESC, LOCALIDADES, CANAL y get_TL(anio)
    (data.datos para el dataset de ejemplo, o un data.procesar.DatosBundle
    para datos subidos). Los 5 colores de COLORES_TIPO se aplican por
    posicion, no por codigo, asi funcionan igual con tipos reales distintos.
    """
    tipos = datos.TIPOS
    tipo_desc = datos.TIPO_DESC
    localidades = datos.LOCALIDADES

    canal = datos.CANAL[anio]
    total_canal = canal[0] + canal[1]
    p_ratio = canal[0] / total_canal if total_canal else 0  # fraccion presencial
    TL = datos.get_TL(anio)

    fig = go.Figure()
    colores = list(COLORES_TIPO.values())

    for i, tipo in enumerate(tipos):
        n_loc = len(localidades)
        datos_pres = [round(TL[i][j] * p_ratio) for j in range(n_loc)]
        datos_virt = [TL[i][j] - datos_pres[j] for j in range(n_loc)]
        color = colores[i % len(colores)]

        # Barra presencial (color solido)
        fig.add_trace(go.Bar(
            name=f"{tipo} - {tipo_desc.get(tipo, tipo)}",
            x=localidades,
            y=datos_pres,
            offsetgroup="presencial",
            legendgroup=tipo,
            marker_color=color,
            hovertemplate=f"<b>{tipo} Presencial</b><br>%{{x}}: %{{y}} exp.<extra></extra>",
        ))

        # Barra virtual (mismo color, mas transparente + borde para que se
        # distinga bien sobre el fondo claro)
        fig.add_trace(go.Bar(
            name=f"{tipo} - {tipo_desc.get(tipo, tipo)}",
            x=localidades,
            y=datos_virt,
            offsetgroup="virtual",
            legendgroup=tipo,
            marker=dict(
                color=hex_to_rgba(color, 0.5),
                line=dict(color=color, width=1),
            ),
            showlegend=False,
            hovertemplate=f"<b>{tipo} Virtual</b><br>%{{x}}: %{{y}} exp.<extra></extra>",
        ))

    # La leyenda de 5 tipos (nombres largos) y la aclaracion "Presencial vs
    # Virtual" no entran juntas arriba del grafico sin superponerse. Se
    # separan: la leyenda de tipos va abajo del grafico (Plotly la
    # acomoda en varias filas si hace falta) y la aclaracion de
    # Presencial/Virtual pasa a ser un st.caption debajo del grafico, fuera
    # del lienzo de Plotly, para que nunca se pisen entre si ni con el titulo.
    fig.update_layout(
        barmode="stack",
        title=dict(
            text="LOCALIDAD × TIPO DE RECLAMO × CANAL DE INGRESO",
            font=dict(size=12, color=TEXT_MUTED),
            x=0,
        ),
        plot_bgcolor=CARD_BG,
        paper_bgcolor=CARD_BG,
        font=dict(color=TEXT_MAIN),
        height=420,
        legend=dict(
            orientation="h",
            yanchor="top", y=-0.16,
            xanchor="center", x=0.5,
            font=dict(size=11),
        ),
        yaxis=dict(
            title="Expedientes",
            gridcolor="rgba(11,33,30,0.10)",
        ),
        xaxis=dict(
            gridcolor="rgba(11,33,30,0.10)",
        ),
        margin=dict(l=60, r=20, t=50, b=120),
    )

    st.plotly_chart(fig, width='stretch')
    st.caption(
        "Barra izquierda = **Presencial** (color sólido) · Barra derecha = "
        "**Virtual** (mismo color, más claro). La leyenda de colores "
        "identifica el tipo de reclamo."
    )
