"""Consulta normativa: RAG sobre normativa, modelos, procedimientos e indicadores (prototipo).

Pestañas: Consulta (chat con fuentes y 👍/👎) · Documentos (subir con arrastrar y soltar, editar, quitar,
búsqueda por significado, reindexar) · Opiniones (votos) · Cómo funciona.
"""
import re
import shutil
import time
from pathlib import Path

import pandas as pd
import streamlit as st

from asistente import config, embeddings, feedback, fragmentos, rag, ui
from asistente.indice import Indice
from asistente.ui import sidebar_ia

ss = st.session_state
ss.setdefault("rag_mensajes", [])
ss.setdefault("rag_uploader", 0)

EJEMPLOS = [
    "¿Qué plazo tiene el ente distribuidor de energía para contestar el traslado?",
    "¿Qué leyes dan competencia a la Entidad para resolver reclamos?",
    "¿Qué código corresponde a baja tensión?",
    "¿En qué plazo debe el ente distribuidor de energía reliquidar las facturas en un caso de sobrefacturación?",
    "¿Cuántos reclamos de sobrefacturación hubo en 2024?",
    "¿Dónde se pierde más tiempo en el circuito de expedientes?",
]
SUBIBLES = ["pdf", "docx", "txt", "md"]


def _marca() -> float:
    p = config.INDICE_DIR / "info.json"
    return p.stat().st_mtime if p.exists() else 0.0


@st.cache_resource(show_spinner="Cargando la base de conocimiento…")
def cargar_indice(_marca: float) -> Indice | None:
    return Indice.cargar()


def reindexar(motor: str, modelo: str | None, host: str, ia_ocr=None) -> bool:
    """Reconstruye el índice con todos los documentos del corpus. Devuelve True si salió bien."""
    with st.status("Reindexando la base de conocimiento…", expanded=True) as estado:
        try:
            nuevo = Indice.construir(motor, modelo or None, "auto", ia_ocr, host, progreso=estado.write)
            nuevo.guardar()
        except Exception as e:  # noqa: BLE001
            estado.update(label=f"No se pudo reindexar: {e}", state="error")
            return False
        errores = [x for x in nuevo.info.get("lecturas", []) if str(x.get("lectura", "")).startswith("error")]
        estado.update(label=f"Listo: {len(nuevo.fragmentos)} fragmentos de {nuevo.info['documentos']} documentos"
                            + (f" · {len(errores)} con error" if errores else ""),
                      state="error" if errores else "complete")
    cargar_indice.clear()
    return True


def config_busqueda(ind: Indice | None) -> tuple[str, str, str]:
    """Motor de embeddings con el que se armó el índice (se reusa al reindexar tras subir archivos)."""
    info = (ind.info if ind else {}) or {}
    motor = info.get("embeddings", "ninguno")
    return motor, info.get("modelo_embeddings", ""), info.get("host_ollama", "http://localhost:11434")


def _nombre_seguro(nombre: str) -> str:
    base = Path(nombre).name
    base = re.sub(r"[^\w.\- áéíóúñÁÉÍÓÚÑ]", "_", base).strip(" .")
    return base.lstrip("_~$") or "documento"


def _guardar_voto(i: int):
    m = ss.rag_mensajes[i]
    v = ss.get(f"rag_fb_{i}")
    if v is None:
        if m.get("id"):
            feedback.quitar(m["id"])
            m["id"] = None
        return
    pregunta = ss.rag_mensajes[i - 1]["content"] if i else ""
    fuentes = [f"[{n}] {f['documento']} — {f['seccion'] or 'texto'}" for n, f in enumerate(m.get("fuentes", []), 1)]
    citadas = [fuentes[n - 1] for n in m.get("citadas", []) if 0 < n <= len(fuentes)]
    m["id"] = feedback.registrar(pregunta, m["content"], "si" if v == 1 else "no", fuentes, citadas,
                                 m.get("motor", ""), id_=m.get("id"))


# ---------------------------------------------------------------------------
# Barra lateral y encabezado
# ---------------------------------------------------------------------------
ia = sidebar_ia()
with st.sidebar:
    st.markdown("### 🔎 Búsqueda")
    tipos = st.multiselect("Buscar en", list(config.TIPOS), format_func=config.TIPOS.get, placeholder="Todas las fuentes")
    top_k = st.slider("Fragmentos por respuesta", 3, 8, config.TOP_K)

st.markdown("## Consulta normativa `PROTOTIPO RAG`")
ui.badge_ia()
ind = cargar_indice(_marca())
motor_actual, modelo_actual, host_actual = config_busqueda(ind)
modo_busqueda = ("palabras clave + significado (" + (modelo_actual or motor_actual) + ")"
                 if motor_actual != "ninguno" else "palabras clave")
st.caption("Preguntá sobre normativa, modelos de resolución y dictamen, procedimientos, códigos e indicadores. "
           f"Cada respuesta cita las fuentes de la base de conocimiento de la Entidad. Búsqueda por {modo_busqueda}.")
if ind is None or not ind.fragmentos:
    st.warning("La base de conocimiento está vacía. Subí documentos en **Documentos** y reindexá.")

tab_chat, tab_docs, tab_op, tab_como = st.tabs(["💬 Consulta", "📂 Documentos", "👍👎 Opiniones", "⚙️ Cómo funciona"])

# ---------------------------------------------------------------------------
# Consulta
# ---------------------------------------------------------------------------
with tab_chat:
    c1, c2 = st.columns([5, 1])
    if c2.button("Nueva consulta", width="stretch"):
        ss.rag_mensajes = []
        for k in [k for k in ss if str(k).startswith(("rag_fb_", "rag_fbc_"))]:
            del ss[k]
        st.rerun()
    if not ss.rag_mensajes:
        c1.markdown("**Probá con alguna de estas preguntas:**")
        cols = st.columns(3)
        for i, ej in enumerate(EJEMPLOS):
            if cols[i % 3].button(ej, key=f"rag_ej_{i}", width="stretch"):
                ss.rag_pendiente = ej
                st.rerun()

    for i, m in enumerate(ss.rag_mensajes):
        with st.chat_message(m["role"]):
            if m.get("aviso"):
                st.warning(m["aviso"], icon="⚠️")
            st.markdown(m["content"])
            if m["role"] != "assistant":
                continue
            if m.get("motor"):
                st.caption(m["motor"])
            if m.get("fuentes"):
                with st.expander(f"Fuentes ({len(m['fuentes'])})"):
                    for n, f in enumerate(m["fuentes"], start=1):
                        marca = "✅" if n in m.get("citadas", []) else "▫️"
                        st.markdown(f"{marca} **[{n}] {f['titulo']}** — {f['seccion'] or 'texto'}  \n"
                                    f"<small>{config.TIPOS.get(f['tipo'], f['tipo'])} · `{f['documento']}`</small>",
                                    unsafe_allow_html=True)
                        st.text(f["texto"][:1200] + ("…" if len(f["texto"]) > 1200 else ""))
            v1, v2 = st.columns([2, 5])
            with v1:
                st.caption("¿Te sirvió la respuesta?")
                st.feedback("thumbs", key=f"rag_fb_{i}", on_change=_guardar_voto, args=(i,))
            if ss.get(f"rag_fb_{i}") == 0 and m.get("id"):
                with v2.popover("¿Qué faltó?"):
                    txt = st.text_area("Comentario", key=f"rag_fbc_{i}", label_visibility="collapsed",
                                       placeholder="Ej.: faltaba el reglamento; citó un documento que no corresponde…")
                    if st.button("Enviar", key=f"rag_fbb_{i}"):
                        feedback.comentar(m["id"], txt)
                        st.toast("Gracias: queda registrado en Opiniones.")

    pregunta = st.chat_input("Escribí tu consulta…", key="rag_input") or ss.pop("rag_pendiente", None)
    if pregunta and ind is not None:
        aviso = ""
        with st.spinner("Buscando en la base de conocimiento…" if ia is None else f"Consultando a {ia.modelo}…"):
            inicio = time.time()
            try:
                r = rag.responder(pregunta, ind, ia, ss.rag_mensajes, top_k, tipos or None)
                motor = f"🟢 Respondido por {ia.nombre} en {time.time() - inicio:.1f} s" if ia else "⚪ Modo sin IA"
                if ia:
                    ui.registrar_exito(ia, time.time() - inicio)
            except Exception as e:  # noqa: BLE001  (si la IA falla, se responde en modo sin IA)
                ui.registrar_error(ia, e)
                aviso = f"No se pudo consultar a la IA: {e}"
                r = rag.responder(pregunta, ind, None, ss.rag_mensajes, top_k, tipos or None)
                motor = "🔴 La IA falló · respuesta en modo sin IA"
            if ind.aviso:
                aviso = (aviso + " " if aviso else "") + ind.aviso
            elif motor_actual != "ninguno":
                motor += " · búsqueda por significado"
            texto, fuentes, citadas = r.texto, [x.fragmento.dict() for x in r.resultados], r.citadas
        ss.rag_mensajes += [{"role": "user", "content": pregunta},
                            {"role": "assistant", "content": texto, "fuentes": fuentes, "citadas": citadas,
                             "motor": motor, "aviso": aviso, "id": None}]
        st.rerun()

# ---------------------------------------------------------------------------
# Documentos
# ---------------------------------------------------------------------------
with tab_docs:
    st.markdown("#### Agregar documentos")
    c1, c2 = st.columns([1, 3])
    tipo = c1.selectbox("Tipo de documento", list(config.TIPOS), format_func=config.TIPOS.get)
    auto = c1.checkbox("Reindexar al guardar", value=True,
                       help="Vuelve a armar el índice para que el chat ya use los documentos nuevos.")
    subidos = c2.file_uploader("Arrastrá los archivos acá o hacé clic para elegirlos (PDF, Word, TXT, Markdown)",
                               type=SUBIBLES, accept_multiple_files=True, key=f"rag_up_{ss.rag_uploader}")
    if subidos:
        destino = config.CORPUS_DIR / tipo
        existentes = [a.name for a in subidos if (destino / _nombre_seguro(a.name)).exists()]
        st.caption(f"{len(subidos)} archivo(s) listos para guardar en **{config.TIPOS[tipo]}**."
                   + (f" Se van a reemplazar: {', '.join(existentes)}." if existentes else ""))
        if st.button("📥 Guardar en la base de conocimiento", type="primary"):
            destino.mkdir(parents=True, exist_ok=True)
            meta = fragmentos.leer_metadatos()
            for a in subidos:
                nombre = _nombre_seguro(a.name)
                (destino / nombre).write_bytes(a.getvalue())
                rel = f"{tipo}/{nombre}"
                meta.setdefault(rel, {"documento": rel, "titulo": Path(nombre).stem.replace("_", " "),
                                      "fecha": "", "vigente": "sí"})
            fragmentos.guardar_metadatos(list(meta.values()))
            ss.rag_uploader += 1                 # vacía la zona de carga
            if auto:
                reindexar(motor_actual, modelo_actual, host_actual)
            st.success(f"Se guardaron {len(subidos)} archivo(s)."
                       + ("" if auto else " Reindexá para que el chat los use."))
            time.sleep(1)
            st.rerun()

    st.markdown("#### Documentos en la base")
    lecturas = {x["documento"]: x for x in ((ind.info.get("lecturas", []) if ind else []))}
    meta = fragmentos.leer_metadatos()
    filas = []
    for p in fragmentos.documentos_corpus():
        rel = str(p.relative_to(config.CORPUS_DIR)).replace("\\", "/")
        m = meta.get(rel, {})
        lec = lecturas.get(rel, {})
        filas.append({"quitar": False, "documento": rel, "tipo": config.TIPOS.get(fragmentos.tipo_de(p), ""),
                      "titulo": m.get("titulo", "") or p.stem.replace("_", " "), "fecha": m.get("fecha", ""),
                      "vigente": m.get("vigente", "") or "sí",
                      "fragmentos": lec.get("fragmentos", 0) if lec else None,
                      "lectura": lec.get("lectura", "sin indexar") if lec else "sin indexar"})
    df = pd.DataFrame(filas)
    if df.empty:
        st.info("Todavía no hay documentos.")
    else:
        ed = st.data_editor(df, hide_index=True, width="stretch", key="rag_docs",
                            disabled=["documento", "tipo", "fragmentos", "lectura"],
                            column_config={
                                "quitar": st.column_config.CheckboxColumn("Quitar", help="Se mueve a _archivados "
                                                                          "(no se borra) y deja de usarse."),
                                "titulo": st.column_config.TextColumn("Título", width="medium"),
                                "fecha": st.column_config.TextColumn("Fecha", help="Ej.: 2024-05-10"),
                                "vigente": st.column_config.SelectboxColumn("Vigente", options=["sí", "no"]),
                                "fragmentos": st.column_config.NumberColumn("Fragmentos"),
                                "lectura": st.column_config.TextColumn("Lectura", help="texto, OCR o error")})
        a1, a2 = st.columns([1, 3])
        if a1.button("💾 Guardar cambios"):
            quitar = ed[ed["quitar"]]["documento"].tolist()
            for rel in quitar:
                origen = config.CORPUS_DIR / rel
                dest = config.ARCHIVADOS_DIR / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                if dest.exists():
                    dest = dest.with_name(f"{dest.stem}_{int(time.time())}{dest.suffix}")
                shutil.move(str(origen), str(dest))
            fragmentos.guardar_metadatos(ed[~ed["quitar"]][["documento", "titulo", "fecha", "vigente"]]
                                         .to_dict("records"))
            if quitar or auto:
                reindexar(motor_actual, modelo_actual, host_actual)
            st.success("Cambios guardados." + (f" Se archivaron {len(quitar)} documento(s)." if quitar else ""))
            time.sleep(1)
            st.rerun()
        a2.caption("Los documentos quitados quedan en `conocimiento/corpus/_archivados/`; para recuperarlos, "
                   "movelos de nuevo a su carpeta y reindexá.")

    st.markdown("#### 🧠 Búsqueda por significado")
    st.caption("Además de las palabras clave, compara el **significado** de la pregunta con cada fragmento "
               "(embeddings), así encuentra respuestas aunque se usen otras palabras: «¿quién firma?» → «EL "
               "DIRECTORIO…». Todo se calcula en esta computadora: los documentos no salen de la PC.")
    motores = list(config.EMBEDDINGS_MOTORES)
    e1, e2, e3 = st.columns([2, 2, 2])
    motor = e1.selectbox("Motor", motores, index=motores.index(motor_actual) if motor_actual in motores else 0,
                         format_func=config.EMBEDDINGS_MOTORES.get)
    modelo_emb = e2.text_input("Modelo", value=(modelo_actual if motor == motor_actual else "")
                               or config.EMBEDDINGS_MODELOS.get(motor, ""), disabled=motor == "ninguno")
    host_emb = e3.text_input("Servidor Ollama local", value=host_actual, disabled=motor != "ollama")
    ok, msg = embeddings.disponible(motor)
    if not ok:
        st.warning(msg)
    if motor == "ollama":
        st.caption("Requiere Ollama instalado en esta PC y el modelo descargado: `ollama pull bge-m3`.")
    elif motor in ("fastembed", "sentence_transformers"):
        st.caption("La primera vez descarga el modelo de internet (unos cientos de MB); después funciona sin conexión.")
    if st.button("🔄 Reindexar con esta configuración", disabled=not ok):
        if reindexar(motor, modelo_emb, host_emb):
            st.success("Índice actualizado.")
            time.sleep(1)
            st.rerun()

# ---------------------------------------------------------------------------
# Opiniones
# ---------------------------------------------------------------------------
with tab_op:
    r = feedback.resumen()
    if not r["total"]:
        st.info("Todavía no hay opiniones. Debajo de cada respuesta podés marcar 👍 o 👎.")
    else:
        m = st.columns(4)
        m[0].metric("Opiniones", r["total"])
        m[1].metric("👍", r["positivos"])
        m[2].metric("👎", r["negativos"])
        m[3].metric("Satisfacción", f"{r['satisfaccion']:.0%}")
        df = feedback.leer()
        solo_neg = st.toggle("Ver solo 👎", value=True)
        if solo_neg:
            df = df[df["voto"] == "no"]
        st.caption("Los 👎 muestran qué documentos faltan o qué preguntas no se encuentran bien.")
        for _, f in df.iloc[::-1].iterrows():
            with st.expander(f"{'👍' if f['voto'] == 'si' else '👎'} {f['fecha']} · {f['pregunta'][:90]}"
                             + (f" · {f['estado']}" if f["voto"] == "no" and f["estado"] else "")):
                if f["comentario"]:
                    st.warning(f["comentario"])
                st.markdown(f["respuesta"])
                st.caption(f"Fuentes: {f['fuentes'] or '—'}  \n{f['calculo']}")
                if f["voto"] == "no":
                    est = st.selectbox("Estado", feedback.ESTADOS, key=f"op_est_{f['id']}",
                                       index=feedback.ESTADOS.index(f["estado"]) if f["estado"] in feedback.ESTADOS else 0)
                    if est != f["estado"]:
                        feedback.cambiar_estado(f["id"], est)
                        st.rerun()
        st.download_button("⬇️ Descargar opiniones (CSV)",
                           feedback.leer().to_csv(sep=";", index=False).encode("utf-8-sig"),
                           "opiniones_consulta.csv", "text/csv")

# ---------------------------------------------------------------------------
# Cómo funciona
# ---------------------------------------------------------------------------
with tab_como:
    st.markdown(f"""
**RAG (Retrieval-Augmented Generation)** = buscar primero y redactar después:

1. **Base de conocimiento:** los documentos (se suben en **Documentos**) se dividen en fragmentos por estructura
   (artículo, considerando, título).
2. **Búsqueda:** la pregunta se compara con los fragmentos por **palabras clave** (BM25, con normalización del
   español: "art. 72" = "artículo 72", "6.753" = "6753"){" y por **significado** (embeddings); las dos listas se combinan" if motor_actual != "ninguno" else ""}.
   Hoy: **{modo_busqueda}**.
3. **Respuesta:** con IA, se envían la pregunta y los fragmentos más relevantes **seudonimizados**, con la
   instrucción de responder solo con esas fuentes y citarlas `[1]`, `[2]`. Sin IA, se muestran los fragmentos.
4. **Mejora continua:** los 👍/👎 quedan en **Opiniones** para detectar qué falta cargar.
""")
    if ind is not None:
        info = ind.info
        m = st.columns(4)
        m[0].metric("Documentos", info.get("documentos", 0))
        m[1].metric("Fragmentos", info.get("fragmentos", 0))
        m[2].metric("Búsqueda", "híbrida" if motor_actual != "ninguno" else "palabras clave")
        m[3].metric("Índice", info.get("creado", "—"))
