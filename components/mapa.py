# components/mapa.py
import streamlit as st
import plotly.graph_objects as go
import numpy as np
from data.datos import CARD_BG, TEXT_MAIN, TEXT_MUTED, MAPA_BUBBLE_COLORSCALE


def render_mapa(anio: str, datos):
    """Renderiza el mapa geografico con burbujas cuyo tamaño Y color reflejan
    la cantidad de expedientes por localidad (doble codificación visual).

    `datos` expone LOCALIDADES, LOCALIDADES_N y COORDS (data.datos para el
    dataset de ejemplo, o un data.procesar.DatosBundle para datos subidos).
    Solo se grafican las localidades que tienen coordenadas conocidas: con
    datos propios, una localidad del top 5 puede no matchear ninguna de las
    conocidas (Capital, La Banda, Termas, Añatuya, Frías) y en ese caso queda
    afuera del mapa (pero sigue apareciendo en el grafico de barras).
    """
    localidades_todas = datos.LOCALIDADES
    n_totales = datos.LOCALIDADES_N[anio]
    coords = datos.COORDS

    pares = [(l, n) for l, n in zip(localidades_todas, n_totales) if l in coords]

    if not pares:
        st.markdown("##### DISTRIBUCIÓN GEOGRÁFICA — RECLAMOS POR LOCALIDAD")
        st.info(
            "Ninguna de las localidades detectadas coincide con las coordenadas "
            "conocidas (Capital, La Banda, Termas, Añatuya, Frías), asi que no "
            "se puede dibujar el mapa para este dataset."
        )
        return

    localidades = [p[0] for p in pares]
    locs_n = [p[1] for p in pares]
    total = sum(n_totales) if sum(n_totales) else 1
    max_n = max(locs_n)
    min_n = min(locs_n)

    lats = [coords[l]["lat"] for l in localidades]
    lons = [coords[l]["lon"] for l in localidades]
    nombres = [coords[l]["nombre_completo"] for l in localidades]
    tipos_f = [coords[l]["tipo_frecuente"] for l in localidades]

    # Escala sqrt para radio de burbujas (max ~50px de diametro)
    sizes = [int(np.sqrt(n / max_n) * 50) if max_n else 0 for n in locs_n]

    hover_texts = [
        f"<b>{nombres[i]}</b><br>"
        f"{locs_n[i]} expedientes · {round(locs_n[i] / total * 100) if total else 0}%<br>"
        f"Tipo más frecuente: {tipos_f[i]}"
        for i in range(len(localidades))
    ]

    fig = go.Figure(go.Scattermap(
        lat=lats,
        lon=lons,
        mode="markers+text",
        marker=go.scattermap.Marker(
            size=sizes,
            sizemode="diameter",
            color=locs_n,
            colorscale=MAPA_BUBBLE_COLORSCALE,
            cmin=min_n,
            cmax=max_n,
            opacity=0.85,
        ),
        text=localidades,
        textposition="bottom center",
        textfont=dict(size=12, color=TEXT_MAIN),
        hovertext=hover_texts,
        hoverinfo="text",
        customdata=locs_n,
    ))

    fig.update_layout(
        map=dict(
            # "open-street-map" dibuja los limites provinciales con una linea
            # mas marcada que "carto-positron" (que los deja casi invisibles).
            # Son tiles prearmados sin token, no se puede tocar el color/grosor
            # de esa linea directamente: si se necesita un contorno exacto en
            # un color propio hay que superponer el GeoJSON real de las
            # provincias (opcion B del documento original, con folium).
            style="open-street-map",
            center=dict(lat=-27.8, lon=-64.0),
            zoom=5.8,
        ),
        title=dict(
            text="DISTRIBUCIÓN GEOGRÁFICA — RECLAMOS POR LOCALIDAD",
            font=dict(size=12, color=TEXT_MUTED),
            x=0,
        ),
        plot_bgcolor=CARD_BG,
        paper_bgcolor=CARD_BG,
        font=dict(color=TEXT_MAIN),
        height=450,
        margin=dict(l=0, r=0, t=50, b=0),
    )

    st.plotly_chart(fig, width='stretch')

    # Leyenda: tamaño Y color codifican lo mismo (cantidad de expedientes).
    # Los colores se toman de MAPA_BUBBLE_COLORSCALE para que nunca queden
    # desincronizados de los que realmente pintan las burbujas.
    col1, col2, col3, _ = st.columns([1, 1, 1, 3])
    colores_escala = [c for _, c in MAPA_BUBBLE_COLORSCALE]
    etiquetas = ["Pocos expedientes", "Cantidad media", "Muchos expedientes"]
    swatches = list(zip([col1, col2, col3], colores_escala, etiquetas))
    for col, color, label in swatches:
        col.markdown(
            f'<span style="display:inline-block;width:10px;height:10px;'
            f'border-radius:50%;background:{color};margin-right:6px;"></span>'
            f'<span style="font-size:0.8rem;color:{TEXT_MUTED};">{label}</span>',
            unsafe_allow_html=True,
        )
