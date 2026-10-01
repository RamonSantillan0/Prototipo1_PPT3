"""Configuración de IA en la barra lateral + indicador de conexión, compartidos por Consulta y Recepción.

La IA es opcional: sin API key (o si la conexión falla), el RAG muestra los fragmentos encontrados y el chatbot
clasifica por reglas. La conexión se PRUEBA de verdad (pedido mínimo al modelo) cuando cambia la configuración,
cada 10 minutos o con el botón «Probar conexión»; el resultado se muestra en la barra lateral y en cada página.
"""
from __future__ import annotations

import os
import time

import streamlit as st

from . import config, llm

ss = st.session_state
VIGENCIA_PRUEBA = 600          # segundos antes de volver a probar la conexión automáticamente

_CSS = """<style>
.ia-pill {display:inline-flex; align-items:center; gap:.4rem; padding:.2rem .7rem; border-radius:999px;
          font-size:13px; font-weight:600; border:1px solid transparent; line-height:1.4;}
.ia-pill .dot {width:.55rem; height:.55rem; border-radius:50%; display:inline-block;}
.ia-ok  {background:#E6F5F3; color:#0B5F56; border-color:#9ED9D0;}  .ia-ok  .dot {background:#0D9488;}
.ia-err {background:#FDECEC; color:#8A1C1C; border-color:#F3B4B4;}  .ia-err .dot {background:#DC2626;}
.ia-off {background:#EEF2F1; color:#33504C; border-color:#DCE6E4;}  .ia-off .dot {background:#94A3A0;}
.ia-det {font-size:12px; color:#33504C; margin-top:.25rem;}
</style>"""


def _secreto(nombre: str) -> str:
    try:
        v = st.secrets.get(nombre, "")
    except Exception:  # noqa: BLE001
        v = ""
    return v or os.environ.get(nombre, "")


@st.cache_data(ttl=600, show_spinner=False)
def _modelos(host: str, api_key: str) -> list[str]:
    try:
        return llm.listar_modelos_ollama(host, api_key)
    except Exception:  # noqa: BLE001
        return []


def _guardar(clave: str):
    ss[f"_ia_{clave}"] = ss[f"w_ia_{clave}"]


def _widget(fn, etiqueta: str, clave: str, defecto, **kw):
    ss.setdefault(f"_ia_{clave}", defecto)
    ss[f"w_ia_{clave}"] = ss[f"_ia_{clave}"]
    return fn(etiqueta, key=f"w_ia_{clave}", on_change=_guardar, args=(clave,), **kw)


# ---------------------------------------------------------------------------
# Estado de la conexión
# ---------------------------------------------------------------------------
def estado() -> dict:
    """{'nivel': 'ok' | 'error' | 'off', 'titulo', 'detalle', 'modelo'} para mostrar en las páginas."""
    return ss.get("_ia_estado_vista", {"nivel": "off", "titulo": "Sin IA", "detalle": "Modo local: no se envía nada "
                                        "a internet.", "modelo": ""})


def _poner_estado(nivel: str, titulo: str, detalle: str = "", modelo: str = ""):
    ss["_ia_estado_vista"] = {"nivel": nivel, "titulo": titulo, "detalle": detalle, "modelo": modelo}


def registrar_error(ia: llm.ProveedorIA | None, error: Exception | str):
    """Una llamada real falló: se marca la conexión como caída hasta la próxima prueba."""
    if ia is None:
        return
    ss["_ia_prueba"] = {"firma": ia.firma(), "estado": llm.EstadoConexion(False, str(error), 0, ia.modelo, time.time())}
    _poner_estado("error", "IA con error", str(error), ia.modelo)


def registrar_exito(ia: llm.ProveedorIA | None, segundos: float):
    if ia is None:
        return
    ss["_ia_prueba"] = {"firma": ia.firma(), "estado": llm.EstadoConexion(True, "Conectado", segundos, ia.modelo,
                                                                          time.time())}
    _poner_estado("ok", "IA conectada", f"{ia.nombre} · última respuesta en {segundos:.1f} s", ia.modelo)


def _probar(ia: llm.ProveedorIA, forzar: bool = False) -> llm.EstadoConexion:
    previo = ss.get("_ia_prueba")
    vigente = (previo and previo["firma"] == ia.firma()
               and time.time() - previo["estado"].cuando < VIGENCIA_PRUEBA)
    if vigente and not forzar:
        return previo["estado"]
    with st.spinner(f"Probando conexión con {ia.modelo}…"):
        est = llm.probar(ia)
    ss["_ia_prueba"] = {"firma": ia.firma(), "estado": est}
    return est


def pill(nivel: str, texto: str) -> str:
    nivel = {"error": "err"}.get(nivel, nivel)
    return f'<span class="ia-pill ia-{nivel}"><span class="dot"></span>{texto}</span>'


def badge_ia():
    """Indicador para el encabezado de cada página."""
    e = estado()
    st.markdown(_CSS, unsafe_allow_html=True)
    texto = {"ok": f"IA conectada · {e['modelo']}", "error": "IA sin conexión · usando modo local",
             "off": "Modo sin IA"}[e["nivel"]]
    st.markdown(pill(e["nivel"], texto), unsafe_allow_html=True, help=e["detalle"])


# ---------------------------------------------------------------------------
# Barra lateral
# ---------------------------------------------------------------------------
def sidebar_ia() -> llm.ProveedorIA | None:
    """Dibuja la configuración de IA. Devuelve el proveedor solo si la conexión fue verificada; si no, None."""
    with st.sidebar:
        st.markdown(_CSS, unsafe_allow_html=True)
        st.markdown("### 🤖 IA (opcional)")
        usar = _widget(st.toggle, "Usar IA", "usar", bool(_secreto("OLLAMA_API_KEY") or _secreto("ANTHROPIC_API_KEY")),
                       help="Sin IA el prototipo funciona igual: el RAG muestra los fragmentos y el chatbot "
                            "clasifica por palabras clave.")
        if not usar:
            _poner_estado("off", "Sin IA", "Modo local: no se envía nada a internet.")
            st.markdown(pill("off", "Modo sin IA"), unsafe_allow_html=True)
            st.markdown('<div class="ia-det">No se envía nada a internet.</div>', unsafe_allow_html=True)
            return None

        proveedor = _widget(st.radio, "Proveedor", "proveedor", "ollama", options=list(config.PROVEEDORES),
                            format_func=config.PROVEEDORES.get, horizontal=True)
        if proveedor == "ollama":
            host = _widget(st.text_input, "Servidor Ollama", "host", config.OLLAMA_HOST_DEFAULT,
                           help="https://ollama.com para Ollama Cloud, o http://localhost:11434 para Ollama local.")
            key = _widget(st.text_input, "API key de Ollama Cloud", "key_ollama", _secreto("OLLAMA_API_KEY"),
                          type="password")
            lista = _modelos(host, key)
            pred = ss.get("_ia_modelo_ollama") or config.OLLAMA_MODELO_DEFAULT
            if lista:
                if ss.get("_ia_modelo_ollama") not in lista:
                    ss["_ia_modelo_ollama"] = pred if pred in lista else lista[0]
                modelo = _widget(st.selectbox, "Modelo", "modelo_ollama", pred, options=lista)
            else:
                modelo = _widget(st.text_input, "Modelo", "modelo_ollama", pred)
            ia = llm.ProveedorIA("ollama", key or "", modelo or "", host, config.OLLAMA_MODELO_VISION)
        else:
            key = _widget(st.text_input, "API key de Anthropic", "key_anthropic", _secreto("ANTHROPIC_API_KEY"),
                          type="password")
            modelo = _widget(st.text_input, "Modelo", "modelo_anthropic", config.MODELO_DEFAULT)
            ia = llm.ProveedorIA("anthropic", key or "", modelo or "")

        if not ia.listo():
            _poner_estado("off", "Sin IA", "Falta la API key: se usa el modo sin IA.")
            st.markdown(pill("off", "Falta la API key"), unsafe_allow_html=True)
            st.markdown('<div class="ia-det">Mientras tanto se usa el modo sin IA.</div>', unsafe_allow_html=True)
            return None

        forzar = st.button("🔄 Probar conexión", width="stretch")
        est = _probar(ia, forzar)
        hace = int(time.time() - est.cuando)
        cuando = "recién" if hace < 60 else f"hace {hace // 60} min"
        if est.ok:
            _poner_estado("ok", "IA conectada", f"{ia.nombre} · respondió en {est.latencia:.1f} s ({cuando})",
                          ia.modelo)
            st.markdown(pill("ok", "Conectado"), unsafe_allow_html=True)
            st.markdown(f'<div class="ia-det"><b>{ia.modelo}</b> · {"local" if ia.es_local else "nube"} · '
                        f'{est.latencia:.1f} s · verificado {cuando}</div>', unsafe_allow_html=True)
            st.caption("Los datos personales se seudonimizan antes de enviarse.")
            return ia
        _poner_estado("error", "IA sin conexión", est.mensaje, ia.modelo)
        st.markdown(pill("err", "Sin conexión"), unsafe_allow_html=True)
        st.error(est.mensaje, icon="⚠️")
        st.caption("Mientras tanto se usa el modo sin IA. Corregí el dato y apretá «Probar conexión».")
        return None
