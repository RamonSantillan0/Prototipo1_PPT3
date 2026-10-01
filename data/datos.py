# data/datos.py
"""
Datos de demostración del dashboard de la Entidad.
Cada vez que se carga el módulo (es decir, cada vez que arranca la app),
se genera un conjunto de datos aleatorio pero coherente: los subtotales
siempre cuadran con los totales, las matrices de heatmap y localidad x tipo
suman correctamente, etc.
"""

import numpy as _np

_rng = _np.random.default_rng()   # semilla diferente en cada arranque


# ── Metadatos fijos ────────────────────────────────────────────────────────────

TIPOS = ["F-17", "S-10", "O-03", "S-07", "F-16"]

TIPO_DESC = {
    "F-17": "Cobro indebido",
    "S-10": "Baja tensión",
    "O-03": "Resarcimiento",
    "S-07": "Demora suministro",
    "F-16": "Sobrefacturación",
}

LOCALIDADES = ["Capital", "La Banda", "Termas", "Añatuya", "Frías"]

MESES = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]

AÑOS = ["Todos los años", "2022", "2023", "2024", "2025", "2026"]

_ANIOS_NUM = [2022, 2023, 2024, 2025, 2026]


# ── Generación aleatoria ───────────────────────────────────────────────────────

def _distribuir(total: int, n: int, pesos=None) -> list[int]:
    """Reparte `total` en `n` enteros positivos con distribución proporcional
    a `pesos` (uniformes si no se dan). La suma siempre es exactamente `total`."""
    if total == 0:
        return [0] * n
    if pesos is None:
        pesos = _rng.dirichlet(_np.ones(n))
    else:
        pesos = _np.array(pesos, dtype=float)
        pesos /= pesos.sum()
    vals = (pesos * total).astype(int)
    diff = total - int(vals.sum())
    for i in _rng.choice(n, size=abs(diff), replace=False):
        vals[i] += 1 if diff > 0 else -1
    return vals.tolist()


def _generar() -> dict:
    """Genera y devuelve todos los datos demo de forma aleatoria."""

    # ── Totales por año ─────────────────────────────────────────────────────
    # El último año (2026) es parcial: ~15-35 % del promedio de los anteriores.
    total_global = int(_rng.integers(1400, 3200))
    # Distribución anual: los primeros 4 años se reparten ~85 % del total;
    # 2026 (parcial) lleva el resto con un tope extra de ruido.
    pesos_anios = _rng.dirichlet([2.5, 3.0, 4.0, 2.5, 0.8])
    totales_anio = _distribuir(total_global, 5, pesos_anios)
    totales_anio_dict = dict(zip([str(a) for a in _ANIOS_NUM], totales_anio))
    totales = {"Todos los años": total_global, **totales_anio_dict}

    anio_anterior = {
        "Todos los años": None,
        "2022": None,
        "2023": totales["2022"],
        "2024": totales["2023"],
        "2025": totales["2024"],
        "2026": totales["2025"],
    }

    # ── Top 5 tipos ─────────────────────────────────────────────────────────
    # Los 5 tipos cubren ~75-92 % del total; el tipo 1 suele ser el mayor.
    pesos_tipos = _rng.dirichlet([5.0, 2.5, 2.0, 1.8, 1.5])
    cobertura = _rng.uniform(0.75, 0.92)

    tipos_n: dict[str, list[int]] = {}
    for clave, total in totales.items():
        subtotal = round(total * cobertura)
        tipos_n[clave] = _distribuir(subtotal, 5, pesos_tipos)

    # ── Canal de ingreso ─────────────────────────────────────────────────────
    pct_presencial = _rng.uniform(0.60, 0.85)
    canal: dict[str, list[int]] = {}
    for clave, total in totales.items():
        pres = round(total * pct_presencial)
        canal[clave] = [pres, total - pres]

    # ── Localidades ──────────────────────────────────────────────────────────
    # Top 5 localidades cubren ~65-85 % del total; Capital suele dominar.
    pesos_locs = _rng.dirichlet([6.0, 3.5, 1.5, 0.8, 0.6])
    cobertura_loc = _rng.uniform(0.65, 0.85)

    localidades_n: dict[str, list[int]] = {}
    for clave, total in totales.items():
        subtotal = round(total * cobertura_loc)
        localidades_n[clave] = _distribuir(subtotal, 5, pesos_locs)

    # ── Heatmap: tipo × mes ──────────────────────────────────────────────────
    # Pesos de estacionalidad: los meses de invierno y comienzo de año tienden
    # a tener más reclamos, pero añadimos ruido para que no siempre sea igual.
    base_mes = _np.array([1.3, 1.2, 1.0, 0.9, 0.8, 0.7, 0.7, 0.9, 0.9, 1.0, 1.1, 1.1])
    base_mes = base_mes * _rng.uniform(0.7, 1.3, size=12)
    base_mes /= base_mes.sum()

    def _heatmap_para(tipo_totales: list[int]) -> list[list[int]]:
        matrix = []
        for tot in tipo_totales:
            pesos_m = base_mes * _rng.uniform(0.5, 1.5, size=12)
            pesos_m /= pesos_m.sum()
            matrix.append(_distribuir(tot, 12, pesos_m))
        return matrix

    heatmap_todos = _heatmap_para(tipos_n["Todos los años"])
    heatmap_por_anio = {
        str(a): _heatmap_para(tipos_n[str(a)])
        for a in _ANIOS_NUM
    }

    # ── Tipo × Localidad ─────────────────────────────────────────────────────
    def _tl_para(tipo_totales: list[int], loc_totales: list[int]) -> list[list[int]]:
        """Distribuye cada tipo entre localidades respetando los pesos de las localidades."""
        total_loc = sum(loc_totales)
        pesos_l = [l / total_loc for l in loc_totales] if total_loc else [1/5]*5
        return [_distribuir(t, 5, pesos_l) for t in tipo_totales]

    tl_todos = _tl_para(tipos_n["Todos los años"], localidades_n["Todos los años"])
    tl_por_anio = {
        str(a): _tl_para(tipos_n[str(a)], localidades_n[str(a)])
        for a in _ANIOS_NUM
    }

    return dict(
        totales=totales,
        anio_anterior=anio_anterior,
        tipos_n=tipos_n,
        canal=canal,
        localidades_n=localidades_n,
        heatmap_todos=heatmap_todos,
        heatmap_por_anio=heatmap_por_anio,
        tl_todos=tl_todos,
        tl_por_anio=tl_por_anio,
    )


_d = _generar()

TOTALES        = _d["totales"]
ANIO_ANTERIOR  = _d["anio_anterior"]
TIPOS_N        = _d["tipos_n"]
CANAL          = _d["canal"]
LOCALIDADES_N  = _d["localidades_n"]
_HEATMAP_TODOS = _d["heatmap_todos"]
_HEATMAP_ANIO  = _d["heatmap_por_anio"]
_TL_TODOS      = _d["tl_todos"]
_TL_ANIO       = _d["tl_por_anio"]

# Año anterior del delta de KPI
filas_sin_fecha = 0
resto_provincial = TOTALES["Todos los años"] - sum(LOCALIDADES_N["Todos los años"])
total_localidades_distintas = 5
total_tipos_distintos = 5


def get_heatmap(anio: str) -> list:
    if anio == "Todos los años":
        return _HEATMAP_TODOS
    return _HEATMAP_ANIO[anio]


def get_TL(anio: str) -> list:
    if anio == "Todos los años":
        return _TL_TODOS
    return _TL_ANIO[anio]


# ── Coordenadas geográficas (fijas, son datos reales) ─────────────────────────
COORDS = {
    "Capital":  {"lat": -27.7951, "lon": -64.2615, "tipo_frecuente": TIPOS[0], "nombre_completo": "Ciudad Capital"},
    "La Banda": {"lat": -27.7117, "lon": -64.1956, "tipo_frecuente": TIPOS[0], "nombre_completo": "La Banda"},
    "Termas":   {"lat": -27.4893, "lon": -64.8645, "tipo_frecuente": TIPOS[0], "nombre_completo": "Termas de Río Hondo"},
    "Añatuya":  {"lat": -28.4608, "lon": -62.8347, "tipo_frecuente": TIPOS[2], "nombre_completo": "Añatuya"},
    "Frías":    {"lat": -28.6463, "lon": -65.1384, "tipo_frecuente": TIPOS[0], "nombre_completo": "Frías"},
}

# Actualizar tipo_frecuente con los datos generados
for _i, _loc in enumerate(LOCALIDADES):
    _tipo_idx = int(_np.argmax([_TL_TODOS[t][_i] for t in range(5)]))
    COORDS[_loc]["tipo_frecuente"] = TIPOS[_tipo_idx]


# ═══════════════════════════════════════════════════════════════════════════════
# PALETA DE COLORES - Estilo 4: "Teal Profesional"
# ═══════════════════════════════════════════════════════════════════════════════

COLOR_PRIMARY      = "#0D9488"
COLOR_PRIMARY_DARK = "#0F766E"
COLOR_PRIMARY_MID  = "#2DD4BF"
COLOR_PRIMARY_DEEP = "#134E4A"
COLOR_PRIMARY_PALE = "#99F6E4"

COLORES_TIPO = {
    "F-17": "#0D9488",
    "S-10": "#0F766E",
    "O-03": "#2DD4BF",
    "S-07": "#134E4A",
    "F-16": "#99F6E4",
}

HEATMAP_COLORSCALE = [
    [0.0,  "#F0FDFA"],
    [0.35, "#CCFBF1"],
    [0.7,  "#5EEAD4"],
    [1.0,  "#2DD4BF"],
]

MAPA_BUBBLE_COLORSCALE = [
    [0.0, "#22C55E"],
    [0.5, "#F97316"],
    [1.0, "#DC2626"],
]

BG_MAIN    = "#EEF2F1"
CARD_BG    = "#FAFCFB"
BORDER     = "#DCE6E4"
TEXT_MAIN  = "#0B211E"
TEXT_MUTED = "#33504C"
