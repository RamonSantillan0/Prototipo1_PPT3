"""Votos 👍/👎 sobre las respuestas de la Consulta normativa, guardados en opiniones/feedback.csv (separado por ;).

Sirven para detectar qué documentos faltan en la base de conocimiento y qué preguntas no se encuentran bien.
La carpeta opiniones/ no se sube a git (las preguntas pueden tener datos personales).
"""
from __future__ import annotations

import csv
import uuid
from datetime import datetime
from pathlib import Path

import pandas as pd

from . import config

COLUMNAS = ["id", "fecha", "voto", "pregunta", "respuesta", "fuentes", "citadas", "calculo", "comentario", "estado"]
ESTADOS = ["pendiente", "falta documento", "resuelta", "descartada"]


def _ruta(ruta: Path | None = None) -> Path:
    return Path(ruta or config.FEEDBACK_CSV)


def leer(ruta: Path | None = None) -> pd.DataFrame:
    p = _ruta(ruta)
    if not p.exists():
        return pd.DataFrame(columns=COLUMNAS)
    df = pd.read_csv(p, sep=";", dtype=str, encoding="utf-8-sig").fillna("")
    for c in COLUMNAS:
        if c not in df:
            df[c] = ""
    return df[COLUMNAS]


def _escribir(df: pd.DataFrame, ruta: Path | None = None) -> None:
    p = _ruta(ruta)
    p.parent.mkdir(parents=True, exist_ok=True)
    df[COLUMNAS].to_csv(p, sep=";", index=False, encoding="utf-8-sig", quoting=csv.QUOTE_MINIMAL)


def registrar(pregunta: str, respuesta: str, voto: str, fuentes: list[str] | None = None,
              citadas: list[str] | None = None, calculo: str = "", comentario: str = "",
              id_: str | None = None, ruta: Path | None = None) -> str:
    """Guarda (o actualiza, si ya existe el id) el voto de una respuesta. voto: "si" / "no". Devuelve el id."""
    df = leer(ruta)
    id_ = id_ or uuid.uuid4().hex[:10]
    fila = {"id": id_, "fecha": datetime.now().strftime("%Y-%m-%d %H:%M"), "voto": voto, "pregunta": pregunta,
            "respuesta": respuesta[:4000], "fuentes": " | ".join(fuentes or []), "citadas": " | ".join(citadas or []),
            "calculo": calculo, "comentario": comentario, "estado": "pendiente" if voto == "no" else ""}
    if (df["id"] == id_).any():
        previo = df.loc[df["id"] == id_].iloc[0]
        if not comentario:
            fila["comentario"] = previo["comentario"]
        df = df[df["id"] != id_]
    _escribir(pd.concat([df, pd.DataFrame([fila])], ignore_index=True), ruta)
    return id_


def quitar(id_: str, ruta: Path | None = None) -> None:
    df = leer(ruta)
    _escribir(df[df["id"] != id_], ruta)


def comentar(id_: str, comentario: str, ruta: Path | None = None) -> None:
    df = leer(ruta)
    df.loc[df["id"] == id_, "comentario"] = comentario
    _escribir(df, ruta)


def cambiar_estado(id_: str, estado: str, ruta: Path | None = None) -> None:
    df = leer(ruta)
    df.loc[df["id"] == id_, "estado"] = estado
    _escribir(df, ruta)


def resumen(ruta: Path | None = None) -> dict:
    df = leer(ruta)
    n = len(df)
    pos = int((df["voto"] == "si").sum())
    return {"total": n, "positivos": pos, "negativos": n - pos, "satisfaccion": pos / n if n else None,
            "pendientes": int(((df["voto"] == "no") & (df["estado"] == "pendiente")).sum())}
