"""Recepción de reclamos: chatbot que simula la Mesa de entrada (prototipo)."""
import time

import pandas as pd
import streamlit as st

from asistente import recepcion as rc
from asistente import ui
from asistente.ui import sidebar_ia

ss = st.session_state
if "bot" not in ss:
    ss.bot = rc.Recepcion()
ss.setdefault("registrados", [])

EJEMPLOS = [
    "Me llegó la factura el doble de lo normal y no consumí más que otros meses",
    "Hace una semana que tengo baja tensión en mi casa, no arranca la heladera",
    "Soy María Gómez, vivo en Belgrano 1234 de La Banda. Ayer hubo un corte y se me quemó el televisor",
    "Toda la cuadra está sin luz desde anoche",
]

ia = sidebar_ia()
bot: rc.Recepcion = ss.bot


def _elegir(opcion: str):
    bot.elegir(opcion, ia)
    _post()


def _post():
    if bot.paso == "registrado" and bot.expediente and not any(
            r["numero"] == bot.expediente["numero"] for r in ss.registrados):
        ss.registrados.append(bot.expediente)


st.markdown("## Recepción de reclamos `PROTOTIPO CHATBOT`")
ui.badge_ia()
st.caption("Simula la Mesa de entrada: el usuario cuenta el problema, el asistente lo clasifica, pide los datos que "
           "faltan, confirma y registra el expediente con su circuito y plazos. Prototipo: no se guarda en ningún sistema.")

col_chat, col_ficha = st.columns([3, 2], gap="large")

with col_chat:
    top = st.columns([4, 1])
    if top[1].button("↺ Reiniciar", width="stretch"):
        ss.bot = rc.Recepcion()
        st.rerun()
    with st.container(height=560, border=True):
        for i, m in enumerate(bot.mensajes):
            with st.chat_message(m["role"], avatar="🏛️" if m["role"] == "assistant" else "🙂"):
                st.markdown(m["content"])
                ultimo = i == len(bot.mensajes) - 1
                if ultimo and m.get("opciones"):
                    cols = st.columns(min(len(m["opciones"]), 3))
                    for j, op in enumerate(m["opciones"]):
                        cols[j % len(cols)].button(op, key=f"op_{i}_{j}", on_click=_elegir, args=(op,),
                                                   width="stretch")
                if ultimo and m.get("elegir_codigo"):
                    cod = st.selectbox("Tipo de reclamo", list(rc.CODIGOS), format_func=rc.etiqueta_codigo,
                                       index=None, placeholder="Buscá por código o nombre…", key=f"sel_{i}")
                    if cod:
                        st.button("Elegir", key=f"selb_{i}", on_click=_elegir, args=(rc.etiqueta_codigo(cod),),
                                  type="primary")
        if bot.paso == "descripcion" and len(bot.mensajes) == 1:
            st.caption("Ejemplos para la demo:")
            for j, ej in enumerate(EJEMPLOS):
                if st.button(ej, key=f"rc_ej_{j}", width="stretch"):
                    ss.rc_pendiente = ej
                    st.rerun()
    texto = st.chat_input("Escribí tu mensaje…", key="rc_input") or ss.pop("rc_pendiente", None)
    if texto:
        with st.spinner("Procesando…" if ia is None else f"Consultando a {ia.modelo}…"):
            inicio = time.time()
            paso_previo = bot.paso
            bot.responder(texto, ia)
        if ia is not None and paso_previo == "descripcion":
            if bot.error_ia:
                ui.registrar_error(ia, bot.error_ia)
            else:
                ui.registrar_exito(ia, time.time() - inicio)
        _post()
        st.rerun()

with col_ficha:
    st.markdown("#### 📋 Ficha del reclamo")
    campos = rc.campos_de(bot.ficha.get("codigo"))
    completos = sum(bool(bot.ficha.get(c.clave)) for c in campos) + bool(bot.ficha.get("codigo"))
    st.progress(completos / (len(campos) + 1), f"{completos} de {len(campos) + 1} datos")
    cod = bot.ficha.get("codigo")
    if cod:
        st.markdown(f"**Tipo:** {rc.etiqueta_codigo(cod)}  \n**Familia:** {rc.FAMILIAS.get(cod[:1], '')}  \n"
                    f"**Área de derivación:** {rc.area_de(cod)}")
    elif bot.candidatos:
        st.markdown("**Tipo sugerido:** " + ", ".join(rc.etiqueta_codigo(c) for c in bot.candidatos))
    if bot.origen_clasificacion:
        st.caption(f"Clasificación por {bot.origen_clasificacion}.")
    if bot.error_ia:
        st.warning(f"La IA falló ({bot.error_ia}); se clasificó por reglas.", icon="⚠️")
    filas = [{"Dato": c.etiqueta, "Valor": bot.ficha.get(c.clave) or "", "": "✅" if bot.ficha.get(c.clave)
              else ("✏️" if bot.pendiente == c.clave else "⬜")} for c in campos]
    st.dataframe(pd.DataFrame(filas)[["", "Dato", "Valor"]], hide_index=True, width="stretch")

    if bot.expediente:
        e = bot.expediente
        st.success(f"Expediente **N° {e['numero']}** · {e['fecha']}")
        st.markdown("**Circuito y plazos estimados** (días hábiles, sin feriados)")
        st.dataframe(pd.DataFrame(e["calendario"]), hide_index=True, width="stretch")
        st.download_button("⬇️ Descargar constancia", bot.constancia().encode("utf-8"),
                           f"constancia_{e['numero']}.txt", "text/plain")
    else:
        with st.expander("¿Cómo sigue el trámite?"):
            st.markdown("Al registrarse, Atención al usuario corre **traslado al ente distribuidor de energía** (7 días hábiles para "
                        "responder). Luego pasa al área técnica o comercial según el tipo, a Asesoría jurídica "
                        "para el dictamen y al Directorio para la resolución.")

if ss.registrados:
    st.divider()
    st.markdown(f"#### Reclamos registrados en esta sesión ({len(ss.registrados)})")
    df = pd.DataFrame([{"Expediente": r["numero"], "Fecha": r["fecha"], "Código": r["codigo"], "Tipo": r["tipo"],
                        "Área": r["area"], "Localidad": r.get("localidad", ""), "Traslado al distribuidor hasta":
                        r["traslado_hasta"]} for r in ss.registrados])
    st.dataframe(df, hide_index=True, width="stretch")
    st.download_button("⬇️ Descargar CSV", df.to_csv(sep=";", index=False).encode("utf-8-sig"),
                       "reclamos_recibidos.csv", "text/csv")
