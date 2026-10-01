"""Normalización de texto en español para la búsqueda por palabras clave."""
from __future__ import annotations

import re
import unicodedata

STOPWORDS = set("""
a al algo algun alguna algunas alguno algunos ante antes asi aun bajo bien cada como con contra cual cuales cuando
de del desde donde dos e el ella ellas ello ellos en entre era eran es esa esas ese eso esos esta estaba estado
estan estar este esto estos fue fueron ha habia han hasta hay la las le les lo los mas me mi mis mucho muy nada ni
no nos o otra otras otro otros para pero poco por porque que quien quienes se segun ser si sido sin sobre son su
sus tal tambien tan tanto te tiene tienen todo todos tu un una unas uno unos y ya cual cuanto cuantos cuantas
dice dicen hace puede pueden debe deben hay
""".split())

_SUFIJOS = ("aciones", "iciones", "amientos", "imientos", "aciones", "acion", "icion", "amiento", "imiento",
            "mente", "idades", "idad", "ables", "ibles", "able", "ible", "istas", "ista", "osos", "osas", "oso",
            "osa", "ivos", "ivas", "ivo", "iva", "ales", "ores", "eras", "eros", "ones", "es", "s", "a", "o", "e")


def sin_tildes(s: str) -> str:
    s = unicodedata.normalize("NFD", s)
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def raiz(p: str) -> str:
    """Stemming liviano para español (suficiente para agrupar singular/plural y derivaciones comunes)."""
    if p.isdigit() or len(p) <= 4:
        return p
    for suf in _SUFIJOS:
        if p.endswith(suf) and len(p) - len(suf) >= 4:
            return p[: -len(suf)]
    return p


_TOKEN = re.compile(r"[a-z0-9]+(?:[.\-/][a-z0-9]+)*")


def tokens(texto: str) -> list[str]:
    t = sin_tildes(texto.lower())
    t = re.sub(r"\bart(?:iculo|\.)?\s*(\d+)", r"articulo \1", t)   # "art. 72" = "artículo 72"
    t = re.sub(r"(\d)\.(\d{3})\b", r"\1\2", t)                      # "6.753" = "6753"
    salida = []
    for tok in _TOKEN.findall(t):
        if tok in STOPWORDS:
            continue
        salida.append(raiz(tok))
    return salida
