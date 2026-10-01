# data/procesar.py
"""
Procesa un CSV (o el .zip de muestra_limpia) subido por el usuario y arma un
"bundle" de datos con la misma interfaz que el modulo data.datos (mismos
nombres de atributos y los metodos get_heatmap(anio) / get_TL(anio)), para
que los componentes (kpi, heatmap, barras, mapa) puedan usar indistintamente
los datos de ejemplo embebidos o los datos reales subidos, sin cambiar su
logica de renderizado.

Nota sobre el formato real (validado contra muestra_limpia.zip): el CSV usa
separador ';' pero encoding UTF-8 (no latin-1 como decia la especificacion
original) - por eso leer_archivo() prueba UTF-8 primero. Ademas las fechas
vienen en formato ISO (AAAA-MM-DD), no DD/MM/AAAA - por eso _preparar()
prueba las dos variantes de parseo y se queda con la que rescata mas filas.
"""
from __future__ import annotations

import io
import unicodedata
import zipfile

import pandas as pd

from data.datos import TIPO_DESC as TIPO_DESC_CONOCIDO, COORDS as COORDS_CONOCIDAS

MESES = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]


def _sin_acentos(texto: str) -> str:
    """Quita acentos/diacriticos para poder comparar 'Frias' con 'Frías',
    'Anatuya' con 'Añatuya', etc. sin depender de que el CSV subido use la
    misma tilde/eñe que los nombres conocidos."""
    nfkd = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def _leer_csv_bytes(nombre: str, contenido: bytes) -> pd.DataFrame:
    """Lee bytes de CSV probando encodings/separadores comunes. Se prueba
    UTF-8 primero (es lo que tiene el dataset real de la Entidad pese a que la
    especificacion original decia latin-1) y se cae a latin-1 despues."""
    intentos = [
        dict(encoding="utf-8", sep=";"),
        dict(encoding="latin-1", sep=";"),
        dict(encoding="utf-8", sep=","),
        dict(encoding="latin-1", sep=","),
    ]
    ultimo_error = None
    for kwargs in intentos:
        try:
            df = pd.read_csv(io.BytesIO(contenido), **kwargs)
            if df.shape[1] >= 2:
                return df
        except Exception as e:  # noqa: BLE001 - queremos probar todas las variantes
            ultimo_error = e
            continue
    try:
        return pd.read_csv(io.BytesIO(contenido), sep=None, engine="python", encoding="utf-8")
    except Exception as e:  # noqa: BLE001
        raise ValueError(f"No se pudo leer '{nombre}': {e}") from (ultimo_error or e)


def leer_archivo(uploaded_file) -> pd.DataFrame:
    """Acepta un .csv suelto o un .zip (como muestra_limpia.zip): si es zip,
    busca dentro un archivo llamado 'reclamos.csv' (o el primer .csv que
    encuentre si no hay ninguno con ese nombre exacto)."""
    uploaded_file.seek(0)
    nombre = getattr(uploaded_file, "name", "") or ""
    contenido = uploaded_file.read()

    if nombre.lower().endswith(".zip") or contenido[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(contenido)) as zf:
            csv_members = [m for m in zf.namelist() if m.lower().endswith(".csv")]
            if not csv_members:
                raise ValueError("El .zip no contiene ningun archivo .csv.")
            elegido = next(
                (m for m in csv_members if m.lower().rsplit("/", 1)[-1] == "reclamos.csv"),
                csv_members[0],
            )
            with zf.open(elegido) as f:
                return _leer_csv_bytes(elegido, f.read())

    return _leer_csv_bytes(nombre or "archivo.csv", contenido)


def sugerir_columna(columnas, palabras_clave) -> str | None:
    """Devuelve la primera columna cuyo nombre contenga alguna palabra clave
    (usado para pre-seleccionar el mapeo de columnas en la UI). El orden de
    palabras_clave importa: las mas especificas van primero para no matchear
    de mas (ej. "cod_reclamo" antes que "reclamo" solo, que tambien aparece
    en columnas como "Numero_reclamo")."""
    for palabra in palabras_clave:
        for c in columnas:
            if palabra.lower() in str(c).lower():
                return c
    return columnas[0] if len(columnas) else None


class DatosBundle:
    """Datos agregados a partir de un CSV subido, con la misma interfaz que
    el modulo data.datos: TOTALES, ANIO_ANTERIOR, TIPOS, TIPO_DESC, CANAL,
    LOCALIDADES, LOCALIDADES_N, COORDS, AÑOS, get_heatmap(anio), get_TL(anio).
    """

    def __init__(self, df: pd.DataFrame, col_tipo: str, col_localidad: str,
                 col_fecha: str, col_canal: str):
        self._preparar(df, col_tipo, col_localidad, col_fecha, col_canal)

    # -- Preparacion --------------------------------------------------------
    def _preparar(self, df: pd.DataFrame, col_tipo, col_localidad, col_fecha, col_canal):
        df = df.copy()

        # Fecha -> año / mes. No asumimos un unico formato: se prueba
        # dayfirst=True (formato argentino DD/MM/AAAA) y dayfirst=False
        # (formato ISO AAAA-MM-DD, que es el que trae realmente
        # muestra_limpia/reclamos.csv) y se usa la variante que logre
        # parsear mas fechas validas. Con dayfirst=True fijo, fechas ISO
        # como "2023-09-13" (dia > 12) se interpretaban mal y quedaban
        # como NaT, descartando de mas filas validas.
        fechas_dayfirst = pd.to_datetime(df[col_fecha], errors="coerce", dayfirst=True)
        fechas_monthfirst = pd.to_datetime(df[col_fecha], errors="coerce", dayfirst=False)
        fechas = fechas_dayfirst if fechas_dayfirst.notna().sum() >= fechas_monthfirst.notna().sum() else fechas_monthfirst
        df["_anio"] = fechas.dt.year
        df["_mes"] = fechas.dt.month
        self.filas_sin_fecha = int(df["_anio"].isna().sum())
        df = df.dropna(subset=["_anio"]).copy()
        if df.empty:
            raise ValueError(
                "Ninguna fila tiene una fecha valida en la columna elegida. "
                "Revisa que sea la columna correcta."
            )
        df["_anio"] = df["_anio"].astype(int)
        df["_mes"] = df["_mes"].astype(int)

        # Canal: si la columna ya viene como Presencial/Virtual se usa tal
        # cual; si es un campo libre tipo "Empl_recibe" se aplica la regla
        # del enunciado original (contiene "VIRTUAL" -> Virtual).
        valores_canal = df[col_canal].astype(str).str.strip().str.upper()
        if set(valores_canal.unique()) <= {"PRESENCIAL", "VIRTUAL", "NAN"}:
            df["_canal"] = valores_canal.replace({"NAN": "PRESENCIAL"}).str.capitalize()
        else:
            df["_canal"] = valores_canal.apply(lambda v: "Virtual" if "VIRTUAL" in v else "Presencial")

        # Tipo: top 5 por frecuencia total (mismo criterio que "Top 5 tipos"
        # del enunciado original)
        df["_tipo"] = df[col_tipo].astype(str).str.strip()
        conteo_tipo = df["_tipo"].value_counts()
        if conteo_tipo.empty:
            raise ValueError("La columna de tipo de reclamo no tiene valores validos.")
        self.TIPOS = list(conteo_tipo.head(5).index)
        self.TIPO_DESC = {t: TIPO_DESC_CONOCIDO.get(t, t) for t in self.TIPOS}

        # Localidad: top 5 por frecuencia + intento de matchear con las
        # coordenadas conocidas (Capital, La Banda, Termas, Añatuya, Frías).
        df["_localidad"] = df[col_localidad].astype(str).str.strip()
        conteo_loc = df["_localidad"].value_counts()
        if conteo_loc.empty:
            raise ValueError("La columna de localidad no tiene valores validos.")
        self.LOCALIDADES = list(conteo_loc.head(5).index)

        self.COORDS = {}
        for loc in self.LOCALIDADES:
            match = self._buscar_coords(loc)
            sub = df[df["_localidad"] == loc]
            tipo_frecuente = sub["_tipo"].value_counts().idxmax() if not sub.empty else "-"
            if match:
                entry = dict(match)
                entry["tipo_frecuente"] = tipo_frecuente
                self.COORDS[loc] = entry
            # si no hay coordenadas conocidas para esa localidad, se la deja
            # fuera del mapa (mapa.py filtra por las que tienen COORDS) pero
            # sigue apareciendo en el grafico de barras.

        # Años disponibles
        anios_presentes = sorted(df["_anio"].unique().tolist())
        self.AÑOS = ["Todos los años"] + [str(a) for a in anios_presentes]

        # Totales / tipos_n / canal / localidades_n por año
        self.TOTALES: dict[str, int] = {}
        self.TIPOS_N: dict[str, list[int]] = {}
        self.CANAL: dict[str, list[int]] = {}
        self.LOCALIDADES_N: dict[str, list[int]] = {}
        self._heatmap_cache: dict[str, list[list[int]]] = {}
        self._tl_cache: dict[str, list[list[int]]] = {}

        grupos = [("Todos los años", df)] + [(str(a), df[df["_anio"] == a]) for a in anios_presentes]
        for clave, subset in grupos:
            self.TOTALES[clave] = int(len(subset))
            self.TIPOS_N[clave] = [int((subset["_tipo"] == t).sum()) for t in self.TIPOS]
            self.CANAL[clave] = [
                int((subset["_canal"] == "Presencial").sum()),
                int((subset["_canal"] == "Virtual").sum()),
            ]
            self.LOCALIDADES_N[clave] = [int((subset["_localidad"] == l).sum()) for l in self.LOCALIDADES]
            self._heatmap_cache[clave] = [
                [int(((subset["_tipo"] == t) & (subset["_mes"] == m)).sum()) for m in range(1, 13)]
                for t in self.TIPOS
            ]
            self._tl_cache[clave] = [
                [int(((subset["_tipo"] == t) & (subset["_localidad"] == l)).sum()) for l in self.LOCALIDADES]
                for t in self.TIPOS
            ]

        # Año anterior (para el delta del KPI de total)
        self.ANIO_ANTERIOR: dict[str, int | None] = {"Todos los años": None}
        for i, a in enumerate(anios_presentes):
            clave = str(a)
            self.ANIO_ANTERIOR[clave] = self.TOTALES[str(anios_presentes[i - 1])] if i > 0 else None

        self.resto_provincial = int(len(df) - sum(self.LOCALIDADES_N["Todos los años"]))
        self.total_localidades_distintas = int(df["_localidad"].nunique())
        self.total_tipos_distintos = int(df["_tipo"].nunique())

    @staticmethod
    def _buscar_coords(nombre_localidad: str):
        nombre_norm = _sin_acentos(nombre_localidad.strip().upper())
        for key, val in COORDS_CONOCIDAS.items():
            key_norm = _sin_acentos(key.upper())
            completo_norm = _sin_acentos(val["nombre_completo"].upper())
            if (
                key_norm in nombre_norm
                or nombre_norm in key_norm
                or completo_norm in nombre_norm
                or nombre_norm in completo_norm
            ):
                return val
        return None

    # -- Interfaz compatible con data.datos ---------------------------------
    def get_heatmap(self, anio: str) -> list:
        return self._heatmap_cache[anio]

    def get_TL(self, anio: str) -> list:
        return self._tl_cache[anio]
