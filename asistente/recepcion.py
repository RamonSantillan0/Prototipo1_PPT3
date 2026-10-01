"""Chatbot de recepción de reclamos (prototipo): simula la Mesa de entrada de la Entidad.

Flujo:
    1. El usuario cuenta el problema con sus palabras.
    2. El bot propone el código de reclamo (F-16, S-10, O-03…) y pide confirmarlo.
    3. Pide, uno por uno, los datos que faltan (los que ya dijo no los vuelve a pedir).
    4. Muestra el resumen para confirmar o corregir.
    5. Registra el reclamo: número de expediente, área de derivación, circuito y fechas estimadas.

Privacidad: los datos personales (nombre, DNI, suministro, domicilio, contacto) se detectan SIEMPRE en la
computadora, con reglas. Si hay IA configurada, solo recibe la descripción del problema SEUDONIMIZADA, para
clasificarla. Sin IA, la clasificación es por palabras clave.
"""
from __future__ import annotations

import random
import re
from dataclasses import dataclass, field
from datetime import date

import numpy as np

from . import config, llm
from .seudonimizador import Seudonimizador
from .textos import sin_tildes

# ---------------------------------------------------------------------------
# Catálogo de códigos (se lee del corpus: conocimiento/corpus/institucional/codigos_de_reclamo.md)
# ---------------------------------------------------------------------------
FAMILIAS = {"F": "Facturación", "M": "Medición", "O": "Otros (daños, atención, fraude)", "S": "Suministro y calidad"}


def _cargar_codigos() -> dict[str, str]:
    ruta = config.CORPUS_DIR / "institucional" / "codigos_de_reclamo.md"
    codigos = {}
    if ruta.exists():
        for m in re.finditer(r"\*\*([FMOS]-\d{2})\*\*:\s*(.+?)\s*$", ruta.read_text(encoding="utf-8"), re.M):
            codigos[m.group(1)] = m.group(2).rstrip(".").strip()
    return codigos or {"F-16": "Sobrefacturación", "S-10": "Baja tensión", "O-03": "Resarcimiento, daños"}


CODIGOS = _cargar_codigos()

# Palabras clave → código (texto normalizado: minúsculas y sin tildes). Peso mayor = más específico.
REGLAS: list[tuple[str, int, str]] = [
    ("F-16", 3, r"sobrefactur|factura\w* (muy |re |demasiado |exageradamente )?(alta|elevad|cara|excesiv|exagerad|abultad)"),
    ("F-16", 3, r"(me|nos) (vino|llego|facturaron|cobraron) (el doble|el triple|mucho|demasiado|una fortuna)"),
    ("F-16", 2, r"(doble|triple|mucho mas|aumento|aumentaron|subio).{0,40}(factura|consumo|boleta)|(factura|boleta|consumo).{0,40}(doble|triple|aumento|subio)"),
    ("F-16", 1, r"\bconsumo\b.{0,30}(no corresponde|no es real|irreal|imposible)"),
    ("F-17", 3, r"cobr\w+ (algo|un cargo|una suma|un concepto|de mas|indebid)|suma indebida|cargo (que )?no corresponde"),
    ("F-15", 3, r"\btasa\b|t\.?e\.?m\b"),
    ("F-04", 3, r"estimad"),
    ("F-03", 3, r"no (me )?(llega|llego|recibi|recibo)\w* (la )?(factura|boleta)|factura no (me )?lleg"),
    ("F-08", 3, r"ya (la )?(pague|abone|pagada|abonada)|factura (ya )?(paga|abonada|pagada)"),
    ("F-01", 3, r"recargo|interes(es)? por mora"),
    ("F-07", 2, r"cuadro tarifario|tarifa (mal|incorrect|equivocad)"),
    ("F-10", 2, r"cambio de tarifa|cambiaron (la|de) tarifa"),
    ("F-11", 3, r"deuda de otro|otro titular|anterior (inquilino|dueno|titular)"),
    ("F-05", 1, r"error(es)? (en|de) (la )?factur"),
    ("S-10", 4, r"baja tension|poca tension|tension baja|voltaje bajo|poca luz|luz (muy )?(debil|baja)|no (arranca|enciende|funciona)n? (la heladera|el aire|los aires|la bomba|el lavarropas)"),
    ("S-11", 4, r"alta tension|sobretension|tension (muy )?alta|voltaje alto"),
    ("S-12", 4, r"oscil|parpade|sube y baja|baja y sube|variacion(es)? de tension|titila"),
    ("S-05", 4, r"cortes? (de luz )?(reiterad|seguid|frecuent|constante|todos los dias|continu)|se corta (la luz )?(todo el tiempo|seguido|a cada rato|todos los dias)"),
    ("S-16", 4, r"sin (previo )?aviso|sin avisar"),
    ("S-09", 4, r"reconex|restitu|(me )?cortaron (la luz )?por (deuda|mora|falta de pago)"),
    ("S-08", 4, r"cortaron .{0,30}(factura|boleta) (ya )?(paga|pagada|abonada)"),
    ("S-07", 3, r"conexion nueva|medidor nuevo|alta del servicio|pedi (el|la) (servicio|conexion)|no me (dan|conectan) (el servicio|la luz)"),
    ("S-06", 3, r"conexion provisoria|provisori"),
    ("S-14", 4, r"poste"),
    ("S-15", 3, r"cable\w*|red (caida|cortada)"),
    ("S-18", 3, r"ramal"),
    ("S-04", 3, r"sin luz .{0,25}(barrio|zona)|(barrio|zona) .{0,25}sin luz|todo el barrio"),
    ("S-03", 3, r"(sin luz|no hay luz) .{0,25}cuadra|cuadra .{0,25}sin luz|toda la cuadra"),
    ("S-02", 3, r"edificio"),
    ("S-01", 2, r"sin luz|no (tengo|hay) luz|no tenemos luz|sin (energia|servicio|suministro)|me quede sin luz|corte de luz|se corto la luz"),
    ("O-03", 5, r"se (me )?(quem|romp|dan|arruin)\w*|quemo|dano\w*|danio|artefacto|electrodomestic|resarc|indemniz"),
    ("M-05", 4, r"medidor .{0,25}(roto|mal|anda|funciona|gira|corre|trabado|quemado)|(roto|mal).{0,15}medidor"),
    ("M-01", 3, r"(cambio|instalacion|colocacion) (de|del) medidor"),
    ("M-06", 3, r"recupero de (energia|consumo)"),
    ("F-14", 4, r"acta de constatacion|brigada|me acusan de (robo|fraude|enganch)"),
    ("O-05", 4, r"fraude|robo de (luz|energia)|enganch"),
    ("O-01", 3, r"(me )?atendieron mal|mala atencion|maltrat|trato (horrible|malo|pesimo)"),
    ("O-04", 3, r"no (me )?atiende\w* (el telefono|la linea|nadie)|nadie atiende"),
    ("O-08", 3, r"cambio de titular"),
    ("O-02", 3, r"vereda|escombro"),
]

# ---------------------------------------------------------------------------
# Área de derivación y circuito (conocimiento/corpus/institucional/circuito_y_plazos.md)
# ---------------------------------------------------------------------------
FRAUDE = {"F-13", "F-14", "F-17", "M-02", "M-03", "M-06", "M-08", "O-05"}
TECNICA_O = {"O-02", "O-03", "O-07", "O-09"}


def area_de(codigo: str) -> str:
    fam = codigo[:1]
    if codigo in FRAUDE:
        return "Asesoría jurídica"
    if fam in ("S", "M") or codigo in TECNICA_O:
        return "Área técnica"
    return "Calidad comercial"


def circuito(codigo: str) -> list[tuple[str, str, int]]:
    """(etapa, responsable, días hábiles) desde el ingreso hasta la notificación."""
    area = area_de(codigo)
    etapas = [("Ingresado", "Mesa de entrada", 1),
              ("Preparar traslado al ente distribuidor de energía", "Atención al usuario", 1),
              ("Traslado al ente distribuidor de energía: espera respuesta", "Ente distribuidor (descargo)", 7),
              ("Respuesta del ente distribuidor de energía: clasificar", "Trámite administrativo", 5)]
    if area == "Área técnica":
        etapas.append(("En Área técnica (informe)", "Área técnica", 60))
    elif area == "Calidad comercial":
        etapas.append(("En Calidad comercial (informe)", "Calidad comercial", 30))
    etapas += [("En Asesoría jurídica (dictamen)", "Asesoría jurídica", 30),
               ("Resolución para firma", "Directorio / Presidencia", 10),
               ("Resolución firmada: notificar", "Trámite administrativo", 5)]
    return etapas


def calendario(codigo: str, desde: date) -> list[dict]:
    """Fechas máximas estimadas sumando días hábiles (sin feriados)."""
    filas, actual = [], np.datetime64(desde, "D")
    for etapa, resp, dias in circuito(codigo):
        fin = np.busday_offset(actual, dias, roll="forward")
        filas.append({"Etapa": etapa, "Responsable": resp, "Días hábiles": dias,
                      "Hasta (estimado)": str(fin.astype(date).strftime("%d/%m/%Y"))})
        actual = fin
    return filas


# ---------------------------------------------------------------------------
# Datos a pedir
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Campo:
    clave: str
    etiqueta: str
    pregunta: str
    ayuda: str = ""


BASICOS = [
    Campo("nombre", "Nombre y apellido", "¿Me decís tu **nombre y apellido**?"),
    Campo("dni", "DNI", "¿Cuál es tu **número de DNI**?", "Solo números, por ejemplo 30123456."),
    Campo("suministro", "N° de suministro", "¿Cuál es el **número de suministro**? Figura en la factura del ente distribuidor de energía.",
          "Es un número de al menos 4 dígitos."),
    Campo("domicilio", "Domicilio del suministro", "¿Cuál es el **domicilio** donde está el suministro? (calle y número)"),
    Campo("localidad", "Localidad", "¿En qué **localidad**?"),
    Campo("contacto", "Teléfono o email", "¿Un **teléfono o email** para avisarte novedades?",
          "Por ejemplo 385 4123456 o nombre@mail.com."),
    Campo("reclamo_distribuidor", "Reclamo previo ante el distribuidor",
          "¿Hiciste antes el **reclamo ante el ente distribuidor de energía**? Si tenés el número, pasamelo; si no, respondé «no»."),
]
POR_FAMILIA = {
    "F": [Campo("periodo", "Factura / período reclamado", "¿Qué **factura o período** reclamás? (por ejemplo, 3er bimestre 2026)"),
          Campo("monto", "Monto facturado", "¿Qué **monto** te facturaron? Si no lo tenés a mano, respondé «no sé».")],
    "S": [Campo("desde", "Desde cuándo", "¿**Desde cuándo** tenés el problema? (fecha aproximada)")],
    "M": [Campo("desde", "Desde cuándo", "¿**Desde cuándo** notás el problema con el medidor?")],
}
DANOS = [Campo("danos", "Artefactos dañados", "¿Qué **artefactos** se dañaron?"),
         Campo("desde", "Fecha del hecho", "¿Qué **día** ocurrió?")]


def campos_de(codigo: str | None) -> list[Campo]:
    if not codigo:
        return list(BASICOS)
    extra = DANOS if codigo == "O-03" else POR_FAMILIA.get(codigo[:1], [])
    return list(BASICOS) + extra


LOCALIDADES = ["Santiago del Estero", "La Banda", "Termas de Río Hondo", "Añatuya", "Frías", "Quimilí", "Clodomira",
               "Loreto", "Fernández", "Beltrán", "Monte Quemado", "Suncho Corral", "Bandera", "Pinto", "Los Juríes",
               "Tintina", "Selva", "Nueva Esperanza", "Sumampa", "Ojo de Agua", "Villa Atamisqui", "Colonia Dora",
               "Herrera", "Icaño", "Campo Gallo", "Pampa de los Guanacos", "Real Sayana", "Villa Unión", "Garza",
               "Forres", "Brea Pozo", "Árraga", "Choya", "Villa Ojo de Agua", "Termas"]
_ALIAS_LOC = {"capital": "Santiago del Estero", "santiago": "Santiago del Estero", "termas": "Termas de Río Hondo",
              "la capital": "Santiago del Estero"}


# ---------------------------------------------------------------------------
# Extracción local (sin IA) de datos personales
# ---------------------------------------------------------------------------
def _n(s: str) -> str:
    return sin_tildes(s.lower())


def _localidad(texto: str) -> str | None:
    t = _n(texto)
    for loc in sorted(LOCALIDADES, key=len, reverse=True):
        if re.search(rf"\b{re.escape(_n(loc))}\b", t):
            return _ALIAS_LOC.get(_n(loc), loc)
    for alias, loc in _ALIAS_LOC.items():
        if re.search(rf"\b{alias}\b", t):
            return loc
    return None


def _titulo(s: str) -> str:
    return " ".join(p.capitalize() if not p.isupper() or len(p) > 3 else p for p in s.split())


def extraer(texto: str, campo: str | None = None) -> dict[str, str]:
    """Busca datos en el texto. Si `campo` es el dato que se acaba de preguntar, acepta respuestas cortas."""
    t = texto.strip()
    tn = _n(t)
    d: dict[str, str] = {}
    # DNI
    m = re.search(r"(?:dni|documento|d\.n\.i\.?)\D{0,12}(\d{1,2}\.?\d{3}\.?\d{3})\b", tn)
    if m:
        d["dni"] = m.group(1).replace(".", "")
    elif campo == "dni":
        m = re.search(r"\b(\d{1,2}\.?\d{3}\.?\d{3})\b", t)
        if m:
            d["dni"] = m.group(1).replace(".", "")
    # Suministro
    m = re.search(r"suministro\D{0,15}(\d[\d\-/]{3,})", tn)
    if m:
        d["suministro"] = m.group(1)
    elif campo == "suministro":
        m = re.search(r"\b(\d[\d\-/]{3,})\b", t)
        if m:
            d["suministro"] = m.group(1)
    # Contacto
    m = re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", t)
    tel = re.search(r"(?:\+?54\s*)?(?:0?\d{3,4}[\s-]?)?(?:15[\s-]?)?\d{3}[\s-]?\d{4}\b", t)
    if m:
        d["contacto"] = m.group(0)
    elif tel and (campo == "contacto" or re.search(r"tel|cel|whats|llam", tn)):
        d["contacto"] = tel.group(0).strip()
    # Nombre
    m = re.search(r"(?i:me llamo|mi nombre es|soy)\s+([A-ZÁÉÍÓÚÑ][a-záéíóúñ]+(?:\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+){1,3})", t)
    if m:
        d["nombre"] = m.group(1)
    elif campo == "nombre":
        limpio = re.sub(r"(?i)^(me llamo|mi nombre es|soy)\s+", "", t).strip(" .")
        if 2 <= len(limpio.split()) <= 5 and not re.search(r"\d", limpio):
            d["nombre"] = _titulo(limpio)
    # Localidad
    loc = _localidad(t)
    if loc and (campo in ("localidad", "domicilio", None) or re.search(r"\b(en|de|vivo)\b", tn)):
        d["localidad"] = loc
    # Domicilio
    m = re.search(r"(?i:vivo en|domicilio(?: es)?|direcci[oó]n(?: es)?|mi casa (?:est[aá]|queda) en)\s*:?\s*"
                  r"((?:calle |av\.? |avenida |barrio |b° )?[A-Za-zÁÉÍÓÚÑáéíóúñ][^,\n\d]{1,35}?\s(?:n[°º.]?\s*)?\d{1,5})\b", t)
    if m and not re.search(r"(?i)suministro|dni|factura", m.group(1)):
        d["domicilio"] = m.group(1).strip(" ,.")
    elif campo == "domicilio" and re.search(r"\d", t):
        dom = t.strip(" .")
        if loc:
            dom = re.sub(rf"(?i),?\s*(de |en )?{re.escape(loc)}.*$", "", dom).strip(" ,.") or dom
        d["domicilio"] = dom
    # Reclamo previo
    if campo == "reclamo_distribuidor":
        num = re.search(r"\d[\d\-/]{2,}", t)
        if num:
            d["reclamo_distribuidor"] = f"Sí, N° {num.group(0)}"
        elif re.match(r"(no|nop|todavia no|aun no|nunca)\b", tn):
            d["reclamo_distribuidor"] = "No"
        elif re.match(r"(si|sí|ya)\b", tn):
            d["reclamo_distribuidor"] = "Sí (sin número)"
    # Monto
    m = re.search(r"\$\s*([\d.]+(?:,\d{1,2})?)|([\d.]+(?:,\d{1,2})?)\s*pesos", t)
    if m:
        d["monto"] = "$ " + (m.group(1) or m.group(2))
    elif campo == "monto":
        if re.search(r"no (se|lo se|tengo|recuerdo)", tn):
            d["monto"] = "No informado"
        else:
            m = re.search(r"\b(\d[\d.]*(?:,\d{1,2})?)\b", t)
            if m:
                d["monto"] = "$ " + m.group(1)
    # Campos de texto libre
    if campo in ("periodo", "desde", "danos") and len(t) >= 2:
        d[campo] = t.strip(" .")
    return d


# ---------------------------------------------------------------------------
# Clasificación
# ---------------------------------------------------------------------------
def clasificar_reglas(texto: str) -> list[tuple[str, int]]:
    tn = _n(texto)
    puntos: dict[str, int] = {}
    for codigo, peso, rx in REGLAS:
        if re.search(rx, tn):
            puntos[codigo] = puntos.get(codigo, 0) + peso
    return sorted(puntos.items(), key=lambda x: -x[1])


SYSTEM_CLASIFICAR = """Clasificás reclamos de usuarios de energía eléctrica contra la distribuidora según una lista de
códigos. Respondé SOLO con JSON: {"codigo": "X-00", "alternativas": ["X-00", "X-00"], "resumen": "una oración"}.
El resumen describe el problema sin datos personales. Usá solo códigos de la lista."""


def clasificar_ia(texto: str, ia: llm.ProveedorIA, datos: dict | None = None) -> tuple[list[str], str]:
    """Solo viaja la descripción seudonimizada: los datos ya detectados en la PC se reemplazan por marcadores."""
    d = datos or {}
    sz = Seudonimizador({"reclamante": d.get("nombre", ""), "domicilio": d.get("domicilio", ""),
                         "identificador": d.get("suministro", "")})
    seudo = sz.seudonimizar(texto)
    for clave in ("dni", "contacto", "suministro"):
        if d.get(clave):
            seudo = seudo.replace(d[clave], f"{{{{{clave.upper()}}}}}")
    lista = "\n".join(f"{c}: {d}" for c, d in CODIGOS.items())
    d = llm.extraer_json(llm.chat(ia, SYSTEM_CLASIFICAR, f"## CÓDIGOS\n{lista}\n\n## RECLAMO\n{seudo}", max_tokens=600))
    cods = [c for c in [d.get("codigo")] + list(d.get("alternativas") or []) if c in CODIGOS]
    return list(dict.fromkeys(cods)), str(d.get("resumen") or "")


# ---------------------------------------------------------------------------
# Conversación
# ---------------------------------------------------------------------------
OTRO = "Otro tipo de reclamo…"
CONFIRMAR = "✅ Confirmar y registrar"
CORREGIR = "✏️ Corregir un dato"
NUEVO = "➕ Registrar otro reclamo"


def etiqueta_codigo(c: str) -> str:
    return f"{c} · {CODIGOS.get(c, '')}"


@dataclass
class Recepcion:
    paso: str = "descripcion"            # descripcion → tipo → datos → resumen → corregir → registrado
    ficha: dict = field(default_factory=dict)
    candidatos: list[str] = field(default_factory=list)
    pendiente: str | None = None
    mensajes: list[dict] = field(default_factory=list)
    origen_clasificacion: str = ""
    error_ia: str = ""                    # último error de la IA (se muestra y se usa el modo por reglas)
    expediente: dict | None = None

    SALUDO = ("¡Hola! Soy el asistente de **Mesa de entrada** de la Entidad. Te ayudo a registrar un reclamo contra "
              "el ente distribuidor de energía.\n\n**Contame con tus palabras qué problema tenés con el servicio.**")

    def __post_init__(self):
        if not self.mensajes:
            self._bot(self.SALUDO)

    # ------------------------------------------------------------------ utilidades
    def _bot(self, texto: str, opciones: list[str] | None = None, elegir_codigo: bool = False):
        self.mensajes.append({"role": "assistant", "content": texto, "opciones": opciones or [],
                              "elegir_codigo": elegir_codigo})

    def faltantes(self) -> list[Campo]:
        return [c for c in campos_de(self.ficha.get("codigo")) if not self.ficha.get(c.clave)]

    def _preguntar_siguiente(self, prefijo: str = ""):
        falta = self.faltantes()
        if falta:
            self.pendiente = falta[0].clave
            self.paso = "datos"
            self._bot((prefijo + "\n\n" if prefijo else "") + falta[0].pregunta)
        else:
            self.pendiente = None
            self.paso = "resumen"
            self._bot((prefijo + "\n\n" if prefijo else "") + "Revisá los datos del reclamo:\n\n" + self.resumen_md()
                      + "\n\n¿Está todo bien?", [CONFIRMAR, CORREGIR])

    def resumen_md(self) -> str:
        filas = [f"- **Tipo:** {etiqueta_codigo(self.ficha['codigo'])}"] if self.ficha.get("codigo") else []
        for c in campos_de(self.ficha.get("codigo")):
            filas.append(f"- **{c.etiqueta}:** {self.ficha.get(c.clave) or '—'}")
        filas.append(f"- **Descripción:** {self.ficha.get('descripcion', '—')}")
        return "\n".join(filas)

    # ------------------------------------------------------------------ entradas
    def responder(self, texto: str, ia: llm.ProveedorIA | None = None):
        texto = texto.strip()
        if not texto:
            return
        self.mensajes.append({"role": "user", "content": texto})
        if re.match(r"(?i)^(reiniciar|empezar de nuevo|nuevo reclamo)\b", texto):
            self.__init__()
            return
        if self.paso == "descripcion":
            return self._descripcion(texto, ia)
        if self.paso == "tipo":
            return self._tipo_texto(texto)
        if self.paso in ("datos", "corregir_dato"):
            return self._dato(texto)
        if self.paso == "resumen":
            if re.match(r"(?i)^(si|sí|ok|dale|confirm|correcto|esta bien|está bien)", texto):
                return self._registrar()
            if re.search(r"(?i)corregir|cambiar|modificar|no\b", texto):
                return self.elegir(CORREGIR)
            self._bot("Si está todo bien, confirmá; si no, elegí qué dato corregir.", [CONFIRMAR, CORREGIR])
            return
        if self.paso == "corregir":
            campo = next((c for c in campos_de(self.ficha.get("codigo"))
                          if _n(c.etiqueta).startswith(_n(texto)[:5])), None)
            return self.elegir(campo.etiqueta if campo else texto)
        if self.paso == "registrado":
            self._bot("El reclamo ya quedó registrado. Si querés cargar otro, tocá el botón.", [NUEVO])

    def elegir(self, opcion: str, ia: llm.ProveedorIA | None = None):
        """Botón elegido por el usuario."""
        if self.paso == "tipo":
            if opcion == OTRO:
                self._bot("Elegí el tipo de reclamo de la lista:", elegir_codigo=True)
                return
            codigo = opcion.split(" · ")[0]
            if codigo in CODIGOS:
                self.mensajes.append({"role": "user", "content": opcion})
                self.ficha["codigo"] = codigo
                self._preguntar_siguiente(f"Perfecto: **{etiqueta_codigo(codigo)}**. Ahora necesito algunos datos.")
            return
        if opcion == CONFIRMAR and self.paso == "resumen":
            self.mensajes.append({"role": "user", "content": opcion})
            return self._registrar()
        if opcion == CORREGIR and self.paso in ("resumen", "corregir"):
            self.mensajes.append({"role": "user", "content": opcion})
            self.paso = "corregir"
            self._bot("¿Qué dato querés corregir?",
                      ["Tipo de reclamo"] + [c.etiqueta for c in campos_de(self.ficha.get("codigo"))])
            return
        if self.paso == "corregir":
            self.mensajes.append({"role": "user", "content": opcion})
            if opcion == "Tipo de reclamo":
                self.paso = "tipo"
                self._bot("Elegí el tipo de reclamo correcto:", elegir_codigo=True)
                return
            campo = next((c for c in campos_de(self.ficha.get("codigo")) if c.etiqueta == opcion), None)
            if campo:
                self.pendiente = campo.clave
                self.paso = "corregir_dato"
                self._bot(campo.pregunta)
            return
        if opcion == NUEVO:
            self.__init__()

    # ------------------------------------------------------------------ pasos
    def _descripcion(self, texto: str, ia):
        self.ficha["descripcion"] = texto
        for k, v in extraer(texto).items():
            self.ficha.setdefault(k, v)
        cods, resumen = [], ""
        if ia is not None and ia.listo():
            try:
                cods, resumen = clasificar_ia(texto, ia, self.ficha)
                self.origen_clasificacion = f"IA · {ia.modelo} (texto seudonimizado)"
                self.error_ia = ""
            except Exception as e:  # noqa: BLE001  (si la IA falla se usan las reglas)
                cods = []
                self.error_ia = str(e)
        if not cods:
            cods = [c for c, _ in clasificar_reglas(texto)]
            self.origen_clasificacion = "reglas (palabras clave)"
        self.candidatos = cods[:3]
        if resumen:
            self.ficha["resumen"] = resumen
        self.paso = "tipo"
        ya = [c.etiqueta.lower() for c in BASICOS if self.ficha.get(c.clave)]
        nota = f"\n\nYa tomé nota de: {', '.join(ya)}." if ya else ""
        if self.candidatos:
            principal = self.candidatos[0]
            self._bot(f"Gracias. Por lo que contás, sería un reclamo de **{etiqueta_codigo(principal)}**.{nota}\n\n"
                      "¿Es correcto? Elegí la opción que mejor lo describa:",
                      [etiqueta_codigo(c) for c in self.candidatos] + [OTRO])
        else:
            self._bot(f"Gracias. No pude identificar el tipo de reclamo con seguridad.{nota}\n\n"
                      "Elegí el tipo de la lista:", elegir_codigo=True)

    def _tipo_texto(self, texto: str):
        m = re.search(r"\b([FMOS])-?(\d{2})\b", texto.upper())
        if m and f"{m.group(1)}-{m.group(2)}" in CODIGOS:
            return self.elegir(etiqueta_codigo(f"{m.group(1)}-{m.group(2)}"))
        if re.match(r"(?i)^(si|sí|correcto|ese|exacto|dale)", texto) and self.candidatos:
            self.mensajes.pop()
            return self.elegir(etiqueta_codigo(self.candidatos[0]))
        cods = [c for c, _ in clasificar_reglas(texto)]
        if cods:
            self.candidatos = cods[:3]
            self._bot("¿Alguno de estos?", [etiqueta_codigo(c) for c in self.candidatos] + [OTRO])
        else:
            self._bot("Elegí el tipo de reclamo de la lista:", elegir_codigo=True)

    def _dato(self, texto: str):
        campo = next(c for c in campos_de(self.ficha.get("codigo")) if c.clave == self.pendiente)
        datos = extraer(texto, campo.clave)
        corrigiendo = self.paso == "corregir_dato"
        if campo.clave not in datos:
            ayuda = f" {campo.ayuda}" if campo.ayuda else ""
            self._bot(f"No me quedó claro.{ayuda}\n\n{campo.pregunta}")
            return
        self.ficha[campo.clave] = datos.pop(campo.clave)
        for k, v in datos.items():                       # datos extra que vinieron en la misma respuesta
            if not self.ficha.get(k) and k in {c.clave for c in campos_de(self.ficha.get("codigo"))}:
                self.ficha[k] = v
        if campo.clave == "reclamo_distribuidor" and self.ficha[campo.clave] == "No":
            prefijo = ("Anotado. Tené en cuenta que la Entidad corre traslado del reclamo al ente distribuidor de energía; si después "
                       "hacés el reclamo ante la distribuidora, guardá el número.")
        else:
            prefijo = "Anotado ✔"
        if corrigiendo:
            self.paso = "resumen"
            self.pendiente = None
            self._bot("Corregido ✔\n\nRevisá los datos del reclamo:\n\n" + self.resumen_md() + "\n\n¿Está todo bien?",
                      [CONFIRMAR, CORREGIR])
            return
        self._preguntar_siguiente(prefijo)

    def _registrar(self):
        hoy = date.today()
        numero = f"{random.randint(1000, 9999)}-{hoy.year}"
        cod = self.ficha["codigo"]
        cal = calendario(cod, hoy)
        self.expediente = {"numero": numero, "fecha": hoy.strftime("%d/%m/%Y"), "codigo": cod,
                           "tipo": CODIGOS.get(cod, ""), "familia": FAMILIAS.get(cod[:1], ""),
                           "area": area_de(cod), "traslado_hasta": cal[2]["Hasta (estimado)"],
                           "calendario": cal, **{k: v for k, v in self.ficha.items()}}
        self.paso = "registrado"
        self._bot(f"✅ **Reclamo registrado.** Expediente **N° {numero}** del {self.expediente['fecha']}.\n\n"
                  f"- **Tipo:** {etiqueta_codigo(cod)}\n"
                  f"- **Próximo paso:** Atención al usuario corre traslado al ente distribuidor de energía, que tiene **SIETE (7) días "
                  f"hábiles** para responder (hasta el {cal[2]['Hasta (estimado)']}, aprox.).\n"
                  f"- **Después:** el expediente pasa a **{self.expediente['area']}** para el informe.\n\n"
                  "Podés descargar la constancia. Te vamos a avisar las novedades al contacto que dejaste.",
                  [NUEVO])

    def constancia(self) -> str:
        e = self.expediente or {}
        lineas = [f"{config.ENTE}", "CONSTANCIA DE RECLAMO (prototipo, sin validez oficial)", "",
                  f"Expediente N°: {e.get('numero')}", f"Fecha: {e.get('fecha')}",
                  f"Tipo de reclamo: {e.get('codigo')} - {e.get('tipo')}", ""]
        for c in campos_de(e.get("codigo")):
            lineas.append(f"{c.etiqueta}: {e.get(c.clave, '')}")
        lineas += ["", f"Descripción: {e.get('descripcion', '')}", "", "Circuito y plazos estimados (días hábiles):"]
        for f in e.get("calendario", []):
            lineas.append(f"  - {f['Etapa']} ({f['Responsable']}): {f['Días hábiles']} días, hasta {f['Hasta (estimado)']}")
        return "\n".join(lineas)
