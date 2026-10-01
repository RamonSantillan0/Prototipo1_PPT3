"""Configuración del asistente (consulta normativa + recepción de reclamos) del dashboard de la Entidad."""
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]           # carpeta del proyecto
CONOCIMIENTO_DIR = BASE_DIR / "conocimiento"
CORPUS_DIR = CONOCIMIENTO_DIR / "corpus"                  # documentos fuente, una subcarpeta por tipo
INDICE_DIR = CONOCIMIENTO_DIR / "indice"                  # índice generado (se puede borrar y regenerar)
ARCHIVADOS_DIR = CORPUS_DIR / "_archivados"               # documentos quitados de la base (no se indexan)
FEEDBACK_CSV = BASE_DIR / "opiniones" / "feedback.csv"    # votos 👍/👎 de la consulta (no se sube a git)
METADATOS_CSV = CORPUS_DIR / "_metadatos.csv"             # título, fecha, vigencia de cada documento

ENTE = "ENTIDAD REGULADORA DE SERVICIOS PÚBLICOS"
ENTE_SIGLA = "la Entidad"
DISTRIBUIDORA = "ente distribuidor de energía"

# Tipos de fuente = subcarpetas de corpus/
TIPOS = {
    "normativa": "Normativa (leyes, reglamentos, contrato)",
    "resoluciones": "Resoluciones",
    "dictamenes": "Dictámenes",
    "indicadores": "Indicadores y análisis",
    "institucional": "Institucional (procedimientos, códigos, criterios)",
}
EXTENSIONES = {".pdf", ".docx", ".txt", ".md", ".png", ".jpg", ".jpeg", ".tif", ".tiff"}

# Fragmentación
MAX_CHARS_FRAGMENTO = 1800
SOLAPE_CHARS = 200

# Recuperación
TOP_K = 5
PESO_EMBEDDINGS = 1.0      # peso de cada lista en la fusión (RRF)
PESO_BM25 = 1.0

# Embeddings: "ninguno" (solo palabras clave) | "fastembed" | "sentence_transformers" | "ollama"
EMBEDDINGS_MOTORES = {
    "ninguno": "Solo palabras clave (BM25) — no requiere instalar nada",
    "fastembed": "fastembed (local, liviano)",
    "sentence_transformers": "sentence-transformers (local)",
    "ollama": "Ollama (local: ollama pull bge-m3)",
}
EMBEDDINGS_MODELOS = {
    "fastembed": "intfloat/multilingual-e5-large",
    "sentence_transformers": "intfloat/multilingual-e5-small",
    "ollama": "bge-m3",
}

# IA para redactar respuestas
PROVEEDORES = {"ollama": "Ollama Cloud", "anthropic": "Claude (Anthropic)"}
MODELO_DEFAULT = "claude-sonnet-4-5"
OLLAMA_HOST_DEFAULT = "https://ollama.com"
OLLAMA_MODELO_DEFAULT = "gpt-oss:120b"
OLLAMA_MODELO_VISION = "gemma4:31b"
OLLAMA_TIMEOUT = 600
