"""Lectura de documentos y división en fragmentos según su estructura.

- Leyes y reglamentos: un fragmento por ARTÍCULO.
- Resoluciones y dictámenes: VISTO, cada CONSIDERANDO (I, II…), DICTAMINA y cada ARTÍCULO.
- Markdown (indicadores, procedimientos): un fragmento por título.
- Otros textos: párrafos agrupados hasta ~1.800 caracteres.
Cada fragmento conserva documento, tipo, título, sección y página para citarlo.
"""
from __future__ import annotations

import csv
import hashlib
import io
import re
from dataclasses import asdict, dataclass
from pathlib import Path

from . import config


@dataclass
class Fragmento:
    id: str
    documento: str         # ruta relativa dentro de corpus/
    tipo: str              # normativa | resoluciones | ...
    titulo: str
    seccion: str
    texto: str
    fecha: str = ""
    vigente: str = "sí"

    def encabezado(self) -> str:
        return f"{self.titulo} — {self.seccion}" if self.seccion else self.titulo

    def para_indexar(self) -> str:
        return f"{self.titulo}. {self.seccion}.\n{self.texto}"

    def dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# Metadatos (corpus/_metadatos.csv): documento;titulo;fecha;vigente
# ---------------------------------------------------------------------------
def leer_metadatos() -> dict[str, dict]:
    if not config.METADATOS_CSV.exists():
        return {}
    with open(config.METADATOS_CSV, encoding="utf-8-sig") as f:
        return {r["documento"]: r for r in csv.DictReader(f, delimiter=";")}


def guardar_metadatos(filas: list[dict]):
    config.METADATOS_CSV.parent.mkdir(parents=True, exist_ok=True)
    with open(config.METADATOS_CSV, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["documento", "titulo", "fecha", "vigente"], delimiter=";")
        w.writeheader()
        for r in filas:
            w.writerow({k: r.get(k, "") for k in ["documento", "titulo", "fecha", "vigente"]})


def documentos_corpus() -> list[Path]:
    return sorted(p for p in config.CORPUS_DIR.rglob("*")
                  if p.is_file() and p.suffix.lower() in config.EXTENSIONES and not p.name.startswith(("_", "~$"))
                  and not any(parte.startswith("_") for parte in p.relative_to(config.CORPUS_DIR).parts[:-1]))


def tipo_de(ruta: Path) -> str:
    rel = ruta.relative_to(config.CORPUS_DIR)
    return rel.parts[0] if len(rel.parts) > 1 and rel.parts[0] in config.TIPOS else "institucional"


# ---------------------------------------------------------------------------
# Lectura
# ---------------------------------------------------------------------------
def texto_docx(datos: bytes) -> str:
    from docx import Document

    d = Document(io.BytesIO(datos))
    partes = [p.text for p in d.paragraphs]
    for t in d.tables:
        for fila in t.rows:
            partes.append(" | ".join(c.text.strip().replace("\n", " ") for c in fila.cells))
    return "\n".join(partes)


def leer_texto(ruta: Path, motor_ocr: str = "auto", ia=None) -> tuple[str, str]:
    """Devuelve (texto, cómo se leyó)."""
    ext = ruta.suffix.lower()
    datos = ruta.read_bytes()
    if ext in (".txt", ".md"):
        return datos.decode("utf-8", errors="replace"), "texto"
    if ext == ".docx":
        return texto_docx(datos), "texto"
    from . import ocr

    doc = ocr.leer(ruta.name, datos, motor_ocr, ia)
    return doc.texto, doc.metodos


# ---------------------------------------------------------------------------
# División
# ---------------------------------------------------------------------------
_ARTICULO = re.compile(r"(?im)^[ \t]*(?:ART[IÍ]CULO|ART\.)[ \t]*(\d+)[ \t]*(?:[°º]|bis)?[ \t]*[.\-:–—]*")
_CONSIDERANDO = re.compile(r"(?m)^[ \t]*([IVXL]{1,6})\.[ \t]+Que\b")
_SECCION_RES = re.compile(r"(?m)^[ \t]*(VISTO|CONSIDERANDO|RESUELVE|DICTAMINA|POR ELLO,?)[ \t]*:?[ \t]*$")
_TITULO_MD = re.compile(r"(?m)^(#{1,3})[ \t]+(.+?)[ \t]*$")


def _partir_largo(texto: str) -> list[str]:
    texto = texto.strip()
    if len(texto) <= config.MAX_CHARS_FRAGMENTO:
        return [texto] if texto else []
    partes, actual = [], ""
    for par in re.split(r"\n\s*\n|\n(?=\s*[a-z]\) )", texto):
        par = par.strip()
        if not par:
            continue
        if actual and len(actual) + len(par) + 2 > config.MAX_CHARS_FRAGMENTO:
            partes.append(actual)
            actual = actual[-config.SOLAPE_CHARS:] + "\n" + par
        else:
            actual = f"{actual}\n\n{par}" if actual else par
        while len(actual) > config.MAX_CHARS_FRAGMENTO * 1.5:          # párrafo gigante
            partes.append(actual[: config.MAX_CHARS_FRAGMENTO])
            actual = actual[config.MAX_CHARS_FRAGMENTO - config.SOLAPE_CHARS:]
    if actual.strip():
        partes.append(actual)
    return partes


def _por_marcas(texto: str, marcas: list[tuple[int, str]]) -> list[tuple[str, str]]:
    """Corta el texto en las posiciones indicadas: [(posición, nombre de sección)]."""
    marcas = sorted(marcas)
    salida = []
    if marcas and marcas[0][0] > 0 and texto[: marcas[0][0]].strip():
        salida.append(("Encabezado", texto[: marcas[0][0]]))
    for i, (pos, nombre) in enumerate(marcas):
        fin = marcas[i + 1][0] if i + 1 < len(marcas) else len(texto)
        salida.append((nombre, texto[pos:fin]))
    return salida


def secciones(texto: str, es_markdown: bool = False) -> list[tuple[str, str]]:
    if es_markdown:
        marcas = []
        ruta: list[str] = []
        for m in _TITULO_MD.finditer(texto):
            nivel = len(m.group(1))
            ruta = ruta[: nivel - 1] + [m.group(2).strip("# ")]
            marcas.append((m.start(), " › ".join(ruta)))
        if marcas:
            return _por_marcas(texto, marcas)
    arts = [(m.start(), f"Artículo {m.group(1)}") for m in _ARTICULO.finditer(texto)]
    cons = [(m.start(), f"Considerando {m.group(1)}") for m in _CONSIDERANDO.finditer(texto)]
    secs = [(m.start(), m.group(1).rstrip(",").capitalize()) for m in _SECCION_RES.finditer(texto)]
    if len(arts) + len(cons) >= 3:
        # en resoluciones, el título "CONSIDERANDO" no hace falta como sección propia si hay considerandos
        secs = [s for s in secs if not (cons and s[1] == "Considerando")]
        return _por_marcas(texto, arts + cons + secs)
    return [("", texto)]


def fragmentar(ruta: Path, texto: str, metadatos: dict | None = None) -> list[Fragmento]:
    rel = str(ruta.relative_to(config.CORPUS_DIR)).replace("\\", "/")
    meta = metadatos or {}
    titulo = meta.get("titulo") or ruta.stem.replace("_", " ")
    tipo = tipo_de(ruta)
    frags = []
    for seccion, cuerpo in secciones(texto, ruta.suffix.lower() == ".md"):
        partes = _partir_largo(cuerpo)
        for n, parte in enumerate(partes, start=1):
            nombre = seccion + (f" (parte {n})" if len(partes) > 1 else "")
            fid = hashlib.md5(f"{rel}|{nombre}|{n}".encode()).hexdigest()[:12]
            frags.append(Fragmento(fid, rel, tipo, titulo, nombre.strip(), parte.strip(),
                                   meta.get("fecha", ""), meta.get("vigente") or "sí"))
    return frags
