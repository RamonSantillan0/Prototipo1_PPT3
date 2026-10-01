"""Dashboard de reclamos (página original del prototipo)."""
import streamlit as st
import data.datos as datos_demo
from data.procesar import DatosBundle, leer_archivo, sugerir_columna
from components.kpi import render_kpi
from components.heatmap import render_heatmap
from components.barras import render_barras
from components.mapa import render_mapa



def formatear_anio(a: str, es_demo: bool) -> str:
    if es_demo and a == "2026":
        return f"{a} (parcial)"
    return a


# ── Header ────────────────────────────────────────────────────────────────────
st.markdown("## Entidad `PROTOTIPO HITO 3`")

# ── Carga de datos ────────────────────────────────────────────────────────────
with st.expander(
    "📂 Cargar dataset propio (reclamos.csv)",
    expanded="datos_bundle" not in st.session_state,
):
    st.caption(
        "Subí el archivo .zip de muestra_limpia tal cual (se busca reclamos.csv "
        "adentro) o el reclamos.csv suelto — separador ';', UTF-8 o latin-1, se "
        "detecta solo."
    )
    archivo = st.file_uploader("Archivo CSV o .zip", type=["csv", "zip"], key="uploader_reclamos")

    if archivo is not None:
        try:
            df_subido = leer_archivo(archivo)
        except Exception as e:
            st.error(f"No se pudo leer el archivo: {e}")
            df_subido = None

        if df_subido is not None and df_subido.shape[1] >= 2:
            columnas = list(df_subido.columns)
            st.write(f"Se detectaron {len(df_subido):,} filas y {len(columnas)} columnas.".replace(",", "."))

            col1, col2 = st.columns(2)
            with col1:
                col_tipo = st.selectbox(
                    "Columna de tipo de reclamo", columnas,
                    index=columnas.index(sugerir_columna(columnas, ["cod_reclamo", "tipo", "cod_tipo", "reclamo"])),
                )
                col_fecha = st.selectbox(
                    "Columna de fecha", columnas,
                    index=columnas.index(sugerir_columna(columnas, ["fecha", "date", "alta"])),
                )
            with col2:
                col_localidad = st.selectbox(
                    "Columna de localidad", columnas,
                    index=columnas.index(sugerir_columna(columnas, ["localidad", "ciudad", "partido"])),
                )
                col_canal = st.selectbox(
                    "Columna de canal / empleado que recibe", columnas,
                    index=columnas.index(sugerir_columna(columnas, ["empl_recibe", "canal", "empleado"])),
                )

            if st.button("Generar gráficos con este archivo", type="primary"):
                try:
                    bundle = DatosBundle(df_subido, col_tipo, col_localidad, col_fecha, col_canal)
                    st.session_state["datos_bundle"] = bundle
                    st.session_state.pop("usar_demo", None)
                    total_ok = bundle.TOTALES["Todos los años"]
                    st.success(
                        f"Listo: {total_ok:,} expedientes procesados "
                        f"({bundle.filas_sin_fecha} filas sin fecha válida se excluyeron)."
                        .replace(",", ".")
                    )
                except Exception as e:
                    st.error(f"No se pudo procesar el archivo con esas columnas: {e}")
        elif df_subido is not None:
            st.error("El archivo no parece tener columnas separadas correctamente (revisá el separador).")

    col_demo, col_vaciar = st.columns(2)
    with col_demo:
        if "datos_bundle" not in st.session_state and not st.session_state.get("usar_demo"):
            if st.button("Ver con datos de ejemplo"):
                st.session_state["usar_demo"] = True
                st.rerun()
    with col_vaciar:
        if "datos_bundle" in st.session_state or st.session_state.get("usar_demo"):
            if st.button("↩ Vaciar dashboard"):
                st.session_state.pop("datos_bundle", None)
                st.session_state.pop("usar_demo", None)
                st.rerun()

usando_datos_propios = "datos_bundle" in st.session_state
usando_demo = st.session_state.get("usar_demo", False)

if usando_datos_propios:
    datos_activo = st.session_state["datos_bundle"]
elif usando_demo:
    datos_activo = datos_demo
else:
    datos_activo = None

# ── Sidebar: filtro global de año ─────────────────────────────────────────────
with st.sidebar:
    st.markdown("### 🗓 Filtro")
    st.markdown("---")

    if datos_activo is not None:
        anio = st.selectbox(
            "Año",
            options=datos_activo.AÑOS,
            index=0,
            format_func=lambda a: formatear_anio(a, usando_demo),
            key="filtro_anio",
        )
        st.caption(
            "Seleccioná un año para filtrar todos los gráficos, "
            "o dejá \"Todos los años\" para ver el período completo."
        )
    else:
        st.selectbox("Año", options=["Todos los años"], disabled=True, key="filtro_anio_vacio")
        st.caption("Cargá un dataset para activar el filtro.")

# ── Contenido principal ───────────────────────────────────────────────────────
if datos_activo is None:
    st.caption("Sistema de gestión de reclamos · sin datos cargados")
    st.divider()
    st.info(
        "El dashboard está vacío. Subí un dataset arriba (.zip o .csv) o "
        "usá el botón \"Ver con datos de ejemplo\" para ver los gráficos."
    )
else:
    if usando_datos_propios:
        st.caption(
            f"Sistema de gestión de reclamos · dataset propio cargado "
            f"({datos_activo.TOTALES['Todos los años']:,} expedientes)".replace(",", ".")
        )
    else:
        st.caption("Sistema de gestión de reclamos · 2022–2026 (datos de ejemplo generados aleatoriamente)")
    st.divider()

    render_kpi(anio, datos_activo)
    render_heatmap(anio, datos_activo)
    render_barras(anio, datos_activo)
    render_mapa(anio, datos_activo)
