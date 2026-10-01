"""Embeddings opcionales (búsqueda por significado). Todos corren en la computadora local.

- "ninguno": no se usan; la búsqueda es solo por palabras clave (BM25).
- "fastembed": liviano (ONNX), descarga el modelo la primera vez.
- "sentence_transformers": requiere PyTorch.
- "ollama": usa un Ollama local (ollama pull bge-m3).
"""
from __future__ import annotations

import numpy as np

from . import config

_cache: dict = {}


def disponible(motor: str) -> tuple[bool, str]:
    if motor == "ninguno":
        return True, ""
    try:
        if motor == "fastembed":
            import fastembed  # noqa: F401
        elif motor == "sentence_transformers":
            import sentence_transformers  # noqa: F401
        elif motor == "ollama":
            import requests  # noqa: F401
        return True, ""
    except ImportError:
        paquete = {"fastembed": "fastembed", "sentence_transformers": "sentence-transformers"}[motor]
        return False, f"Falta instalar: pip install {paquete}"


def _prefijo(textos: list[str], modelo: str, consulta: bool) -> list[str]:
    if "e5" in modelo.lower():                       # los modelos E5 esperan estos prefijos
        return [("query: " if consulta else "passage: ") + t for t in textos]
    return textos


def _normalizar(m: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(m, axis=1, keepdims=True)
    n[n == 0] = 1
    return (m / n).astype("float32")


def vectorizar(textos: list[str], motor: str, modelo: str | None = None, consulta: bool = False,
               host: str = "http://localhost:11434") -> np.ndarray:
    modelo = modelo or config.EMBEDDINGS_MODELOS.get(motor, "")
    textos = _prefijo(textos, modelo, consulta)
    if motor == "fastembed":
        from fastembed import TextEmbedding

        clave = ("fe", modelo)
        if clave not in _cache:
            _cache[clave] = TextEmbedding(model_name=modelo)
        return _normalizar(np.array(list(_cache[clave].embed(textos))))
    if motor == "sentence_transformers":
        from sentence_transformers import SentenceTransformer

        clave = ("st", modelo)
        if clave not in _cache:
            _cache[clave] = SentenceTransformer(modelo)
        return _normalizar(np.array(_cache[clave].encode(textos, batch_size=16, show_progress_bar=False)))
    if motor == "ollama":
        import requests

        vectores = []
        for i in range(0, len(textos), 32):
            r = requests.post(f"{host.rstrip('/')}/api/embed", json={"model": modelo, "input": textos[i:i + 32]},
                              timeout=300)
            r.raise_for_status()
            vectores += r.json()["embeddings"]
        return _normalizar(np.array(vectores))
    raise ValueError(f"Motor de embeddings desconocido: {motor}")
