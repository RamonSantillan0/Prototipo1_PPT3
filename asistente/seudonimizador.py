"""Seudonimización reversible de datos personales antes de enviar texto a la IA.

Reemplaza los datos personales por marcadores como {{USUARIO}}, {{DOMICILIO}}
o {{PERSONA_2}}. La tabla de equivalencias queda SOLO en la computadora local;
cuando vuelve la respuesta de la IA, los marcadores se reemplazan por los datos
reales.

Detecta:
  * Datos conocidos del expediente: nombre del reclamante (en ambos órdenes y
    el apellido solo), domicilio del suministro e identificador del usuario.
  * Nombres extra que cargue la persona (vecinos, peritos, testigos…).
  * Por patrón: DNI, CUIT/CUIL, correos, teléfonos, CBU, N.º de medidor,
    domicilios del tipo "Calle N° 123" y nombres precedidos de Sr./Sra./Dr./Dra.

No es infalible: siempre revisar la vista previa antes de enviar.
"""
from __future__ import annotations

import re
import unicodedata

# Palabras que preceden a "N°" y NO son domicilios (normas, notas, expedientes…)
_NO_DOMICILIO = {
    "ley", "leyes", "resolucion", "resoluciones", "res", "decreto", "dto", "nota", "notas",
    "expediente", "expte", "exp", "dictamen", "articulo", "art", "acta", "actas", "factura",
    "facturas", "disposicion", "contrato", "orden", "suministro", "legajo", "reclamo", "medidor",
    "cuenta", "cliente", "usuario", "ticket", "tramite", "inciso", "anexo", "circular", "punto",
    "folio", "fs", "pericia", "informe", "codigo", "cod", "recibo", "poliza", "presupuesto",
}

_PATRONES: list[tuple[str, re.Pattern]] = [
    ("EMAIL", re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")),
    ("CUIT", re.compile(r"\b(?:20|23|24|27|30|33|34)-?\d{8}-?\d\b")),
    ("CBU", re.compile(r"\b\d{22}\b")),
    ("DNI", re.compile(r"(?i)\b(?:D\.?\s?N\.?\s?I\.?|documento(?:\s+de\s+identidad)?)\s*(?:N[°º.o]*\s*)?:?\s*\d{1,2}\.?\d{3}\.?\d{3}\b")),
    ("DNI", re.compile(r"(?<![$\d.,])(?<!\$ )\b\d{1,2}\.\d{3}\.\d{3}\b")),
    ("TELEFONO", re.compile(r"(?i)(?:tel(?:[eé]fono)?|cel(?:ular)?)\.?\s*:?\s*[\d\s()+-]{7,}\d"
                            r"|(?<![\w$.,])(?:\+?54\s?9?\s?)?\(?0?\d{2,4}\)?[\s-]?(?:15[\s-]?)?\d{3,4}[\s-]?\d{3,4}\b")),
    ("MEDIDOR", re.compile(r"(?i)\bmedidor\s*(?:N[°º.o]*\s*)?:?\s*[A-Z0-9-]*\d[A-Z0-9-]*")),
    ("SUMINISTRO", re.compile(r"(?i)\bsuministro\s*(?:N[°º.o]*\s*)?:?\s*[A-Z]{0,3}-?\d(?:[\d/.-]*\d)?")),
]
_DOMICILIO = re.compile(
    r"\b(?:(?:[Cc]alle|[Aa]v(?:enida|da)?\.?|[Pp]asaje|[Pp]je\.?|[Bb]arrio|B[°º])\s+)?"
    r"([A-ZÁÉÍÓÚÑ][\wáéíóúñ.]*(?:\s+(?:de\s+)?[A-ZÁÉÍÓÚÑ0-9][\wáéíóúñ.]*){0,3})\s*N[°º]\s*\d{1,5}\b"
)
_NOMBRE = r"(?:[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+|[A-ZÁÉÍÓÚÑ]{2,})"
_TRATAMIENTO = re.compile(
    r"\b(?:Sr|Sra|Srta|Dr|Dra|Ing|Lic|[Ss]eñor|[Ss]eñora|[Uu]suari[oa](?:/a)?|[Tt]itular|[Rr]eclamante|"
    r"[Ff]irmante|[Ff]irma|[Ff]irmado(?: por)?|[Ss]uscribe|[Ss]uscripto/?a?|[Ss]uscrito/?a?|[Rr]equirente|"
    r"[Nn]ombre(?: y apellido)?|[Aa]pellido y nombre)[.,:]?\s+"
    r"(" + _NOMBRE + r"(?:,?\s+" + _NOMBRE + r"){0,3})"
)
# Palabras que, si aparecen, indican que no es un nombre de persona
_NO_PERSONA = {"entidad", "distribuidor", "edese", "enrese", "empresa", "distribuidora", "ente", "sa", "s.a", "suministro", "energia",
               "santiago", "estero", "del", "de", "la", "resolucion", "expediente", "asesoria", "area"}
# Acepta {{USUARIO}} y también {USUARIO}, por si el modelo pierde una llave
_MARCADOR = re.compile(r"\{\{?([A-Z_]+(?:_\d+)?)\}?\}")


def _normalizar(s: str) -> str:
    s = unicodedata.normalize("NFD", s.lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


class Seudonimizador:
    def __init__(self, ficha: dict | None = None, extras: list[str] | None = None):
        self.tabla: dict[str, str] = {}      # marcador -> valor real
        self._inversa: dict[str, str] = {}   # valor normalizado -> marcador
        self._conocidos: list[tuple[str, str]] = []   # (texto, marcador), del más largo al más corto
        self._contador: dict[str, int] = {}
        if ficha:
            self._registrar_ficha(ficha)
        for nombre in extras or []:
            if nombre.strip():
                self._conocido(nombre.strip(), self._nuevo("PERSONA", nombre.strip()))

    # ------------------------------------------------------------------ registro
    def _nuevo(self, tipo: str, valor: str, unico: bool = False) -> str:
        clave = _normalizar(valor)
        if clave in self._inversa:
            return self._inversa[clave]
        if unico:
            marcador = f"{{{{{tipo}}}}}"
        else:
            self._contador[tipo] = self._contador.get(tipo, 0) + 1
            marcador = f"{{{{{tipo}_{self._contador[tipo]}}}}}"
        self.tabla[marcador] = valor
        self._inversa[clave] = marcador
        return marcador

    def _conocido(self, texto: str, marcador: str):
        if len(texto) >= 3:
            self._conocidos.append((texto, marcador))
            self._conocidos.sort(key=lambda t: -len(t[0]))

    def _registrar_ficha(self, f: dict):
        nombre = (f.get("reclamante") or "").strip()
        if nombre:
            m = self._nuevo("USUARIO", nombre, unico=True)
            partes = nombre.split()
            self._conocido(nombre, m)
            if len(partes) >= 2:
                # "Juárez Silvia" -> también "Silvia Juárez" y el apellido solo
                self._conocido(" ".join(partes[1:] + partes[:1]), m)
                if len(partes[0]) >= 4:
                    self._conocido(partes[0], m)
        dom = (f.get("domicilio") or "").strip()
        if dom:
            self._conocido(dom, self._nuevo("DOMICILIO", dom, unico=True))
        ident = (f.get("identificador") or "").strip()
        if ident:
            self._conocido(ident, self._nuevo("ID_SUMINISTRO", ident, unico=True))

    # ------------------------------------------------------------------ uso
    def seudonimizar(self, texto: str) -> str:
        if not texto:
            return texto
        # 1) datos conocidos (sin distinguir mayúsculas ni tildes)
        for original, marcador in self._conocidos:
            patron = re.compile(r"(?<!\w)" + _patron_flexible(original) + r"(?!\w)", re.I)
            texto = patron.sub(marcador, texto)
        # 2) patrones
        for tipo, patron in _PATRONES:
            texto = patron.sub(lambda m, t=tipo: self._nuevo(t, m.group(0)), texto)
        texto = _DOMICILIO.sub(self._sub_domicilio, texto)
        antes = len(self._conocidos)
        texto = _TRATAMIENTO.sub(self._sub_persona, texto)
        # 3) los nombres encontrados por contexto se buscan también en el resto del texto
        #    (en otro orden, sin tildes o en mayúsculas: "GOMEZ MARIA LAURA" = "María Laura Gómez")
        if len(self._conocidos) > antes:
            for original, marcador in self._conocidos:
                patron = re.compile(r"(?<!\w)" + _patron_flexible(original) + r"(?!\w)", re.I)
                texto = patron.sub(marcador, texto)
        return texto

    def _sub_domicilio(self, m: re.Match) -> str:
        palabras = {_normalizar(w).strip(".") for w in m.group(1).split()}
        if palabras & _NO_DOMICILIO:
            return m.group(0)
        return self._nuevo("DOMICILIO", m.group(0))

    def _sub_persona(self, m: re.Match) -> str:
        if "{{" in m.group(0):
            return m.group(0)
        palabras = {_normalizar(w).strip(".,") for w in m.group(1).split()}
        if palabras & _NO_PERSONA:
            return m.group(0)
        tratamiento = m.group(0)[: m.start(1) - m.start(0)]
        nombre = m.group(1)
        marcador = self._nuevo("PERSONA", nombre)
        partes = nombre.replace(",", " ").split()
        variantes = {" ".join(partes)}
        if len(partes) >= 2:
            variantes.add(" ".join(partes[1:] + partes[:1]))      # apellido al final
            variantes.add(" ".join(partes[-1:] + partes[:-1]))     # apellido al principio
        for v in variantes:
            if (v, marcador) not in self._conocidos:
                self._conocido(v, marcador)
        return tratamiento + marcador

    def reidentificar(self, texto: str) -> str:
        return _MARCADOR.sub(lambda m: self.tabla.get("{{" + m.group(1) + "}}", m.group(0)), texto or "")

    def reidentificar_obj(self, obj):
        if isinstance(obj, str):
            return self.reidentificar(obj)
        if isinstance(obj, list):
            return [self.reidentificar_obj(x) for x in obj]
        if isinstance(obj, dict):
            return {k: self.reidentificar_obj(v) for k, v in obj.items()}
        return obj

    def reemplazos(self) -> list[dict]:
        return [{"Marcador": k, "Dato real (no se envía)": v} for k, v in self.tabla.items()]


def _patron_flexible(texto: str) -> str:
    """Patrón que ignora tildes y admite espacios variables."""
    equivalentes = {"a": "[aá]", "e": "[eé]", "i": "[ií]", "o": "[oó]", "u": "[uúü]", "n": "[nñ]"}
    salida = []
    for c in _normalizar(texto):
        if c.isspace():
            salida.append(r"\s+")
        elif c in "°º":
            salida.append(r"[°º]\s*")
        else:
            salida.append(equivalentes.get(c, re.escape(c)))
    return "".join(salida)
