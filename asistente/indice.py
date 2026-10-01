"""Índice híbrido: BM25 (palabras clave) + embeddings opcionales, fusionados con RRF.

Todo se guarda en la carpeta indice/ como archivos (JSON + NumPy): no hace falta
ninguna base de datos. Se puede borrar y regenerar cuando cambian los documentos.
"""
from __future__ import annotations

import json
import math
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from . import config, embeddings
from .fragmentos import Fragmento, documentos_corpus, fragmentar, leer_metadatos, leer_texto
from .textos import tokens


@dataclass
class Resultado:
    fragmento: Fragmento
    puntaje: float
    rank_bm25: int | None = None
    rank_emb: int | None = None


@dataclass
class Indice:
    fragmentos: list[Fragmento] = field(default_factory=list)
    info: dict = field(default_factory=dict)
    # BM25
    _tf: list[Counter] = field(default_factory=list)
    _df: Counter = field(default_factory=Counter)
    _largos: list[int] = field(default_factory=list)
    _vectores: np.ndarray | None = None
    aviso: str = ""                      # se completa si la búsqueda por significado no estuvo disponible

    # ------------------------------------------------------------------ construcción
    @classmethod
    def construir(cls, motor_emb: str = "ninguno", modelo_emb: str | None = None, motor_ocr: str = "auto",
                  ia=None, host_ollama: str = "http://localhost:11434", progreso=None) -> "Indice":
        def paso(m):
            if progreso:
                progreso(m)

        meta = leer_metadatos()
        frags: list[Fragmento] = []
        lecturas = []
        for ruta in documentos_corpus():
            rel = str(ruta.relative_to(config.CORPUS_DIR)).replace("\\", "/")
            paso(f"Leyendo {rel}…")
            try:
                texto, metodo = leer_texto(ruta, motor_ocr, ia)
            except Exception as e:  # noqa: BLE001
                lecturas.append({"documento": rel, "lectura": f"error: {e}", "fragmentos": 0})
                continue
            nuevos = fragmentar(ruta, texto, meta.get(rel))
            frags += nuevos
            lecturas.append({"documento": rel, "lectura": metodo, "fragmentos": len(nuevos), "caracteres": len(texto)})
        ind = cls(frags)
        ind._armar_bm25()
        if motor_emb != "ninguno" and frags:
            paso(f"Calculando embeddings ({len(frags)} fragmentos)…")
            ind._vectores = embeddings.vectorizar([f.para_indexar() for f in frags], motor_emb, modelo_emb,
                                                  host=host_ollama)
        ind.info = {"creado": time.strftime("%Y-%m-%d %H:%M"), "fragmentos": len(frags),
                    "documentos": len(lecturas), "embeddings": motor_emb,
                    "modelo_embeddings": modelo_emb or config.EMBEDDINGS_MODELOS.get(motor_emb, ""),
                    "host_ollama": host_ollama, "lecturas": lecturas}
        return ind

    def _armar_bm25(self):
        self._tf = [Counter(tokens(f.para_indexar())) for f in self.fragmentos]
        self._df = Counter()
        for tf in self._tf:
            self._df.update(tf.keys())
        self._largos = [sum(tf.values()) for tf in self._tf]

    # ------------------------------------------------------------------ guardar / cargar
    def guardar(self, carpeta: Path | None = None):
        carpeta = Path(carpeta or config.INDICE_DIR)
        carpeta.mkdir(parents=True, exist_ok=True)
        (carpeta / "fragmentos.json").write_text(json.dumps([f.dict() for f in self.fragmentos], ensure_ascii=False),
                                                 encoding="utf-8")
        (carpeta / "info.json").write_text(json.dumps(self.info, ensure_ascii=False, indent=2), encoding="utf-8")
        vec = carpeta / "vectores.npy"
        if self._vectores is not None:
            np.save(vec, self._vectores)
        elif vec.exists():
            vec.unlink()

    @classmethod
    def cargar(cls, carpeta: Path | None = None) -> "Indice | None":
        carpeta = Path(carpeta or config.INDICE_DIR)
        if not (carpeta / "fragmentos.json").exists():
            return None
        frags = [Fragmento(**d) for d in json.loads((carpeta / "fragmentos.json").read_text(encoding="utf-8"))]
        ind = cls(frags, json.loads((carpeta / "info.json").read_text(encoding="utf-8")))
        ind._armar_bm25()
        if (carpeta / "vectores.npy").exists():
            ind._vectores = np.load(carpeta / "vectores.npy")
        return ind

    # ------------------------------------------------------------------ búsqueda
    def _bm25(self, consulta: str, k1: float = 1.5, b: float = 0.75) -> np.ndarray:
        n = len(self.fragmentos)
        prom = (sum(self._largos) / n) if n else 1
        q = tokens(consulta)
        puntajes = np.zeros(n, dtype="float32")
        for t in set(q):
            df = self._df.get(t, 0)
            if not df:
                continue
            idf = math.log(1 + (n - df + 0.5) / (df + 0.5))
            for i, tf in enumerate(self._tf):
                f = tf.get(t, 0)
                if f:
                    puntajes[i] += idf * f * (k1 + 1) / (f + k1 * (1 - b + b * self._largos[i] / prom))
        return puntajes

    def buscar(self, consulta: str, k: int = config.TOP_K, tipos: list[str] | None = None,
               solo_vigentes: bool = False) -> list[Resultado]:
        if not self.fragmentos:
            return []
        permitido = np.array([(not tipos or f.tipo in tipos) and (not solo_vigentes or f.vigente.lower() != "no")
                              for f in self.fragmentos])
        rrf = np.zeros(len(self.fragmentos), dtype="float32")
        ranks_b, ranks_e = {}, {}

        bm = np.where(permitido, self._bm25(consulta), -1)
        orden_b = [i for i in np.argsort(-bm) if bm[i] > 0][:50]
        for r, i in enumerate(orden_b):
            rrf[i] += config.PESO_BM25 / (60 + r + 1)
            ranks_b[i] = r + 1

        self.aviso = ""
        qv = None
        if self._vectores is not None:
            try:
                qv = embeddings.vectorizar([consulta], self.info["embeddings"], self.info.get("modelo_embeddings"),
                                           consulta=True, host=self.info.get("host_ollama", "http://localhost:11434"))[0]
            except Exception as e:  # noqa: BLE001  (sin el modelo de embeddings, se busca solo por palabras clave)
                self.aviso = (f"La búsqueda por significado no está disponible ({str(e)[:120]}); "
                              "se buscó solo por palabras clave.")
        if qv is not None:
            sim = np.where(permitido, self._vectores @ qv, -1)
            for r, i in enumerate(np.argsort(-sim)[:50]):
                rrf[i] += config.PESO_EMBEDDINGS / (60 + r + 1)
                ranks_e[i] = r + 1

        orden = [i for i in np.argsort(-rrf) if rrf[i] > 0][:k]
        return [Resultado(self.fragmentos[i], float(rrf[i]), ranks_b.get(i), ranks_e.get(i)) for i in orden]
