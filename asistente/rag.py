"""RAG básico: recuperar fragmentos del corpus, armar el prompt y pedir la respuesta con citas.

Sin IA configurada devuelve los fragmentos encontrados (modo demostración sin internet)."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from . import config, llm
from .indice import Indice, Resultado
from .seudonimizador import Seudonimizador

SYSTEM = f"""Sos el asistente interno de consulta de la {config.ENTE} ({config.ENTE_SIGLA}). Respondés preguntas del \
personal (Asesoría Jurídica, áreas técnica y comercial, Trámite, Directorio) sobre normativa, resoluciones, \
dictámenes, procedimientos e indicadores de reclamos contra el {config.DISTRIBUIDORA}.

Reglas:
1. Respondé SOLO con la información de las FUENTES que se te pasan. No uses conocimiento propio sobre leyes, \
números de artículo, plazos ni cifras.
2. Citá cada afirmación con el número de la fuente entre corchetes, por ejemplo [2] o [1][3].
3. Si las fuentes no alcanzan para responder, decilo claramente ("No lo encontré en las fuentes cargadas") y, si \
sirve, indicá qué documento habría que agregar.
4. Si una fuente está marcada como NO VIGENTE, aclaralo.
5. Las cifras de indicadores se informan tal cual figuran, indicando el período. Si la fuente advierte que los datos \
pueden ser de prueba, mencionalo.
6. Los modelos de resolución y dictamen tienen campos entre corchetes ([FECHA], [MONTO]): son plantillas, no casos reales.
7. Respondé en español, claro y breve. Usá viñetas o una tabla corta si ayuda.
8. Los datos personales pueden venir reemplazados por marcadores como {{{{PERSONA_1}}}}: copialos tal cual."""


@dataclass
class Respuesta:
    texto: str
    resultados: list[Resultado]
    consulta_busqueda: str
    prompt: str = ""
    citadas: list[int] = field(default_factory=list)


def _consulta_con_contexto(pregunta: str, historial: list[dict]) -> str:
    """Para preguntas de seguimiento cortas ("¿y en 2023?"), suma la pregunta anterior a la búsqueda."""
    previas = [m["content"] for m in historial if m["role"] == "user"]
    corta = len(pregunta.split()) <= 6 or re.match(r"(?i)^\s*(y|e|pero|entonces|tambi[eé]n|ese|esa|eso)\b", pregunta)
    return f"{previas[-1]} {pregunta}" if previas and corta else pregunta


def _fuentes(resultados: list[Resultado]) -> str:
    bloques = []
    for i, r in enumerate(resultados, start=1):
        f = r.fragmento
        vig = "" if f.vigente.lower() != "no" else " — NO VIGENTE"
        fecha = f" ({f.fecha})" if f.fecha else ""
        bloques.append(f"[{i}] {f.titulo}{fecha} — {f.seccion or 'texto'} · tipo: {config.TIPOS.get(f.tipo, f.tipo)}"
                       f"{vig}\n{f.texto}")
    return "\n\n".join(bloques)


def preparar(pregunta: str, indice: Indice, historial: list[dict] | None = None, k: int = config.TOP_K,
             tipos: list[str] | None = None, solo_vigentes: bool = False, seudonimizar: bool = True):
    historial = historial or []
    consulta = _consulta_con_contexto(pregunta, historial)
    resultados = indice.buscar(consulta, k, tipos, solo_vigentes)
    conversacion = "\n".join(f"{'Usuario' if m['role'] == 'user' else 'Asistente'}: {m['content'][:600]}"
                             for m in historial[-6:])
    mensaje = (f"## CONVERSACIÓN PREVIA\n{conversacion or '(ninguna)'}\n\n"
               f"## FUENTES\n{_fuentes(resultados) or '(no se encontraron fragmentos)'}\n\n"
               f"## PREGUNTA\n{pregunta}")
    sz = Seudonimizador() if seudonimizar else None
    if sz:
        mensaje = sz.seudonimizar(mensaje)
    return mensaje, resultados, consulta, sz


def responder(pregunta: str, indice: Indice, ia: llm.ProveedorIA | None, historial: list[dict] | None = None,
              k: int = config.TOP_K, tipos: list[str] | None = None, solo_vigentes: bool = False,
              seudonimizar: bool = True) -> Respuesta:
    mensaje, resultados, consulta, sz = preparar(pregunta, indice, historial, k, tipos, solo_vigentes, seudonimizar)
    if not resultados:
        return Respuesta("No encontré nada relacionado en las fuentes cargadas. Probá con otras palabras o agregá "
                         "el documento en **Fuentes**.", [], consulta, mensaje)
    if ia is None or not ia.listo():
        def limpio(t: str, n: int) -> str:
            t = re.sub(r"(?m)^#{1,6}\s*(.+)$", r"**\1**", t.strip())
            return t[:n].rsplit(" ", 1)[0] + "…" if len(t) > n else t
        principal = resultados[0].fragmento
        otras = "\n".join(f"- [{i}] {r.fragmento.encabezado()}" for i, r in enumerate(resultados[1:4], start=2))
        texto = (f"**Modo sin IA** — el fragmento más relevante es **[1] {principal.encabezado()}**:\n\n"
                 f"> {limpio(principal.texto, 700).replace(chr(10), chr(10) + '> ')}\n\n"
                 + (f"Otras fuentes relacionadas:\n{otras}\n\n" if otras else "")
                 + "_Activá la IA en la barra lateral para obtener una respuesta redactada con citas._")
        return Respuesta(texto, resultados, consulta, mensaje, [1])
    texto = llm.chat(ia, SYSTEM, mensaje, json_salida=False, max_tokens=2500).strip()
    if sz:
        texto = sz.reidentificar(texto)
    citadas = sorted({int(n) for n in re.findall(r"\[(\d+)\]", texto) if 0 < int(n) <= len(resultados)})
    return Respuesta(texto, resultados, consulta, mensaje, citadas)
