"""Lectura de documentos del expediente, incluidos PDF escaneados y fotos.

Para cada página:
  1. Si el PDF tiene texto digital, se usa ese texto (rápido y exacto).
  2. Si es un escaneo, se aplica OCR:
       - Tesseract (local, los datos no salen de la computadora), o
       - un modelo de IA con visión (nube), si Tesseract no está instalado o si se elige.
"""
from __future__ import annotations

import io
import os
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from . import llm

MOTORES = {
    "auto": "Automático: Tesseract si está instalado; si no, IA con visión",
    "tesseract": "Tesseract (local, nada sale de la computadora)",
    "ia": "IA con visión (nube: se envía la imagen)",
}
EXT_IMAGEN = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}
EXT_TEXTO = {".txt", ".md"}
MIN_CHARS_TEXTO_DIGITAL = 40      # menos que esto en una página = se trata como escaneo
DPI_OCR = 300

SYSTEM_OCR = ("Sos un transcriptor de documentos administrativos argentinos escaneados. Transcribí el texto de la "
              "imagen de forma literal y completa, respetando párrafos, números, fechas y montos. No resumas, no "
              "corrijas y no agregues comentarios. Si una parte es ilegible, escribí [ilegible]. Si hay sellos o "
              "firmas, indicá [firma] o [sello]. Devolvé solo el texto.")

_RUTAS_TESSERACT_WINDOWS = [
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Programs\Tesseract-OCR\tesseract.exe"),
]


@dataclass
class Pagina:
    archivo: str
    numero: int
    metodo: str            # "texto" | "tesseract" | "ia" | "error"
    texto: str
    aviso: str = ""


@dataclass
class Documento:
    nombre: str
    paginas: list[Pagina] = field(default_factory=list)

    @property
    def texto(self) -> str:
        return "\n\n".join(f"[Página {p.numero}]\n{p.texto}" if len(self.paginas) > 1 else p.texto
                           for p in self.paginas)

    @property
    def metodos(self) -> str:
        cuenta: dict[str, int] = {}
        for p in self.paginas:
            cuenta[p.metodo] = cuenta.get(p.metodo, 0) + 1
        nombres = {"texto": "texto digital", "tesseract": "OCR Tesseract", "ia": "OCR con IA", "error": "error"}
        return ", ".join(f"{n} pág. {nombres.get(m, m)}" for m, n in cuenta.items())


# ---------------------------------------------------------------------------
# Tesseract
# ---------------------------------------------------------------------------
def tesseract_info() -> dict:
    """{'ok': bool, 'ruta': str, 'idiomas': [...], 'spa': bool, 'motivo': str}"""
    try:
        import pytesseract
    except ImportError:
        return {"ok": False, "motivo": "Falta el paquete pytesseract (pip install pytesseract)."}
    ruta = shutil.which("tesseract") or next((r for r in _RUTAS_TESSERACT_WINDOWS if Path(r).exists()), None)
    if not ruta:
        return {"ok": False, "motivo": "Tesseract no está instalado (ver README)."}
    pytesseract.pytesseract.tesseract_cmd = ruta
    try:
        idiomas = pytesseract.get_languages(config="")
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "ruta": ruta, "motivo": f"No se pudo ejecutar Tesseract: {e}"}
    return {"ok": True, "ruta": ruta, "idiomas": idiomas, "spa": "spa" in idiomas,
            "motivo": "" if "spa" in idiomas else "Tesseract no tiene el idioma español (spa): se usa inglés."}


def _ocr_tesseract(img_bytes: bytes) -> str:
    import pytesseract
    from PIL import Image, ImageOps

    info = tesseract_info()
    if not info["ok"]:
        raise RuntimeError(info["motivo"])
    img = ImageOps.autocontrast(Image.open(io.BytesIO(img_bytes)).convert("L"))
    return pytesseract.image_to_string(img, lang="spa" if info["spa"] else "eng")


def _ocr_ia(img_bytes: bytes, ia: llm.ProveedorIA) -> str:
    if ia is None or not ia.listo():
        raise RuntimeError("Para leer escaneos con IA hace falta configurar el proveedor y la API key.")
    return llm.chat(ia, SYSTEM_OCR, "Transcribí el texto de esta página.", imagenes=[_achicar(img_bytes)],
                    json_salida=False, modelo=ia.modelo_vision or ia.modelo, max_tokens=4000).strip()


def _achicar(img_bytes: bytes, ancho_max: int = 1700) -> bytes:
    from PIL import Image

    img = Image.open(io.BytesIO(img_bytes)).convert("L")
    if img.width > ancho_max:
        img = img.resize((ancho_max, int(img.height * ancho_max / img.width)))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def ocr_imagen(img_bytes: bytes, motor: str, ia: llm.ProveedorIA | None) -> tuple[str, str, str]:
    """Devuelve (texto, método, aviso)."""
    if motor == "tesseract" or (motor == "auto" and tesseract_info()["ok"]):
        info = tesseract_info()
        return _ocr_tesseract(img_bytes), "tesseract", info.get("motivo", "")
    return _ocr_ia(img_bytes, ia), "ia", ""


# ---------------------------------------------------------------------------
# Archivos
# ---------------------------------------------------------------------------
def leer(nombre: str, datos: bytes, motor: str = "auto", ia: llm.ProveedorIA | None = None,
         progreso=None) -> Documento:
    """Lee un archivo del expediente y devuelve su texto página por página."""
    ext = Path(nombre).suffix.lower()
    doc = Documento(nombre)

    def paso(msg):
        if progreso:
            progreso(msg)

    try:
        if ext == ".pdf":
            import pymupdf

            pdf = pymupdf.open(stream=datos, filetype="pdf")
            for i, page in enumerate(pdf, start=1):
                texto = page.get_text().strip()
                if len(texto) >= MIN_CHARS_TEXTO_DIGITAL:
                    doc.paginas.append(Pagina(nombre, i, "texto", texto))
                    continue
                paso(f"OCR de {nombre}, página {i} de {len(pdf)}")
                png = page.get_pixmap(dpi=DPI_OCR, colorspace=pymupdf.csGRAY).tobytes("png")
                doc.paginas.append(_pagina_ocr(nombre, i, png, motor, ia))
        elif ext in EXT_IMAGEN:
            from PIL import Image, ImageSequence

            img = Image.open(io.BytesIO(datos))
            for i, frame in enumerate(ImageSequence.Iterator(img), start=1):
                paso(f"OCR de {nombre}, imagen {i}")
                buf = io.BytesIO()
                frame.convert("RGB").save(buf, format="PNG")
                doc.paginas.append(_pagina_ocr(nombre, i, buf.getvalue(), motor, ia))
        elif ext == ".docx":
            from .fragmentos import texto_docx

            doc.paginas.append(Pagina(nombre, 1, "texto", texto_docx(datos)))
        elif ext in EXT_TEXTO:
            doc.paginas.append(Pagina(nombre, 1, "texto", datos.decode("utf-8", errors="replace")))
        else:
            doc.paginas.append(Pagina(nombre, 1, "error", "", f"Formato no soportado: {ext}"))
    except Exception as e:  # noqa: BLE001
        doc.paginas.append(Pagina(nombre, len(doc.paginas) + 1, "error", "", f"No se pudo leer: {e}"))
    return doc


def limpiar_ocr(texto: str) -> str:
    """Correcciones típicas del OCR: 'N*', 'N”', 'Nº' -> 'N° ' antes de un número; espacios de más."""
    texto = re.sub(r"\bN\s?[*”\"“'º°o]\s*(?=\d)", "N° ", texto)
    texto = re.sub(r"[ \t]{2,}", " ", texto)
    return texto


def _pagina_ocr(nombre, numero, png, motor, ia) -> Pagina:
    try:
        texto, metodo, aviso = ocr_imagen(png, motor, ia)
        texto = limpiar_ocr(texto)
        if len(texto.strip()) < 15:
            aviso = (aviso + " " if aviso else "") + "Casi no se reconoció texto: revisar la calidad del escaneo."
        return Pagina(nombre, numero, metodo, texto.strip(), aviso.strip())
    except Exception as e:  # noqa: BLE001
        return Pagina(nombre, numero, "error", "", str(e))
