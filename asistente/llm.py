"""Cliente único para los modelos de IA (Ollama Cloud / Ollama local / Claude).

- `chat()` envía un pedido y devuelve el texto de la respuesta.
- `probar()` verifica de verdad la conexión (servidor + API key + modelo) con un pedido mínimo.
- Todos los errores se convierten en `ErrorIA` con un mensaje claro en español, para mostrarlo en pantalla.
"""
from __future__ import annotations

import base64
import json
import re
import time
from dataclasses import dataclass

from . import config

TIMEOUT_PRUEBA = 30          # segundos para la prueba de conexión (los modelos en la nube pueden tardar en "despertar")


class ErrorIA(RuntimeError):
    """Error de conexión o de respuesta del modelo, con mensaje listo para mostrar."""


@dataclass
class ProveedorIA:
    proveedor: str = "ollama"            # "ollama" | "anthropic"
    api_key: str = ""
    modelo: str = config.OLLAMA_MODELO_DEFAULT
    host: str | None = None              # solo Ollama
    modelo_vision: str = ""              # para leer escaneos; vacío = el mismo modelo

    @property
    def es_local(self) -> bool:
        return self.proveedor == "ollama" and bool(self.host) and "ollama.com" not in (self.host or "")

    def listo(self) -> bool:
        """Tiene lo mínimo para intentar conectarse (no garantiza que la conexión funcione: ver probar())."""
        return bool(self.modelo) and (bool(self.api_key.strip()) or self.es_local)

    @property
    def nombre(self) -> str:
        donde = "Ollama local" if self.es_local else config.PROVEEDORES.get(self.proveedor, self.proveedor)
        return f"{self.modelo} · {donde}"

    def firma(self) -> str:
        """Identifica la configuración (sin exponer la key) para saber cuándo hay que volver a probar."""
        k = self.api_key.strip()
        return f"{self.proveedor}|{self.host or ''}|{self.modelo}|{len(k)}:{k[-4:]}"


# ---------------------------------------------------------------------------
# Pedidos
# ---------------------------------------------------------------------------
def chat(ia: ProveedorIA, system: str, usuario: str, imagenes: list[bytes] | None = None,
         json_salida: bool = True, modelo: str | None = None, max_tokens: int = 8000,
         timeout: float | None = None) -> str:
    modelo = modelo or ia.modelo
    if not ia.listo():
        raise ErrorIA("Falta la API key o el modelo.")
    if ia.proveedor == "anthropic":
        texto = _anthropic(ia, system, usuario, imagenes, modelo, max_tokens, timeout)
    else:
        texto = _ollama(ia, system, usuario, imagenes, json_salida, modelo, timeout, max_tokens)
    return texto


def _anthropic(ia, system, usuario, imagenes, modelo, max_tokens, timeout) -> str:
    try:
        import anthropic
    except ImportError as e:
        raise ErrorIA("Para usar Claude falta instalar el paquete: pip install anthropic") from e

    contenido = []
    for img in imagenes or []:
        contenido.append({"type": "image", "source": {"type": "base64", "media_type": _mime(img),
                                                      "data": base64.b64encode(img).decode()}})
    contenido.append({"type": "text", "text": usuario})
    try:
        client = anthropic.Anthropic(api_key=ia.api_key.strip(), timeout=timeout or config.OLLAMA_TIMEOUT,
                                     max_retries=1)
        resp = client.messages.create(model=modelo, max_tokens=max_tokens, system=system,
                                      messages=[{"role": "user", "content": contenido}])
    except anthropic.AuthenticationError as e:
        raise ErrorIA("Anthropic rechazó la API key (401). Revisala en console.anthropic.com.") from e
    except anthropic.NotFoundError as e:
        raise ErrorIA(f"Anthropic no encontró el modelo «{modelo}».") from e
    except anthropic.RateLimitError as e:
        raise ErrorIA("Se alcanzó el límite de uso de Anthropic (429). Probá en unos minutos.") from e
    except anthropic.APITimeoutError as e:
        raise ErrorIA("Anthropic no respondió a tiempo.") from e
    except anthropic.APIConnectionError as e:
        raise ErrorIA("No se pudo conectar con Anthropic. Revisá la conexión a internet.") from e
    except anthropic.APIStatusError as e:
        raise ErrorIA(f"Anthropic respondió {e.status_code}: {str(e)[:200]}") from e
    return "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")


def _ollama(ia, system, usuario, imagenes, json_salida, modelo, timeout, max_tokens=8000) -> str:
    import requests

    host = (ia.host or config.OLLAMA_HOST_DEFAULT).strip().rstrip("/")
    headers = {"Content-Type": "application/json"}
    if ia.api_key.strip():
        headers["Authorization"] = f"Bearer {ia.api_key.strip()}"
    msg_usuario = {"role": "user", "content": usuario}
    if imagenes:
        msg_usuario["images"] = [base64.b64encode(i).decode() for i in imagenes]
    body = {"model": modelo, "messages": [{"role": "system", "content": system}, msg_usuario],
            "stream": False, "options": {"temperature": 0.1}}
    if json_salida:
        body["format"] = "json"
    if max_tokens < 100:                              # prueba de conexión: respuesta corta y rápida
        body["options"]["num_predict"] = max_tokens
    limite = timeout or config.OLLAMA_TIMEOUT
    try:
        r = requests.post(f"{host}/api/chat", json=body, headers=headers, timeout=limite)
    except requests.exceptions.Timeout as e:
        raise ErrorIA(f"El modelo no respondió en {limite:.0f} s ({host}).") from e
    except requests.exceptions.ConnectionError as e:
        local = "¿Está abierto Ollama en esta PC? " if "localhost" in host or "127.0.0.1" in host else ""
        raise ErrorIA(f"No se pudo conectar con {host}. {local}Revisá la conexión a internet o la dirección.") from e
    except requests.exceptions.RequestException as e:
        raise ErrorIA(f"Error de red al conectar con {host}: {e}") from e
    if r.status_code in (401, 403):
        raise ErrorIA("Ollama rechazó la API key (401). Revisala en ollama.com → Settings → Keys.")
    if r.status_code == 404:
        raise ErrorIA(f"Ollama no encontró el modelo «{modelo}» (404). Elegí otro de la lista.")
    if r.status_code == 429:
        raise ErrorIA("Se alcanzó el límite de uso de Ollama Cloud (429). Probá en unos minutos.")
    if r.status_code >= 400:
        raise ErrorIA(f"Ollama respondió {r.status_code}: {r.text[:300]}")
    try:
        datos = r.json()
    except ValueError as e:
        raise ErrorIA(f"La respuesta de {host} no es válida (¿la dirección es correcta?).") from e
    if datos.get("error"):
        raise ErrorIA(f"Ollama: {datos['error']}")
    return datos.get("message", {}).get("content", "")


# ---------------------------------------------------------------------------
# Prueba de conexión
# ---------------------------------------------------------------------------
@dataclass
class EstadoConexion:
    ok: bool
    mensaje: str
    latencia: float = 0.0
    modelo: str = ""
    cuando: float = 0.0


def probar(ia: ProveedorIA, timeout: float = TIMEOUT_PRUEBA) -> EstadoConexion:
    """Pedido mínimo al modelo: confirma que el servidor responde, la key es válida y el modelo existe."""
    inicio = time.time()
    try:
        chat(ia, "Respondé solo con la palabra OK.", "OK?", json_salida=False, max_tokens=5, timeout=timeout)
    except ErrorIA as e:
        return EstadoConexion(False, str(e), time.time() - inicio, ia.modelo, time.time())
    except Exception as e:  # noqa: BLE001
        return EstadoConexion(False, f"Error inesperado: {e}", time.time() - inicio, ia.modelo, time.time())
    return EstadoConexion(True, "Conectado", time.time() - inicio, ia.modelo, time.time())


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------
def _mime(img: bytes) -> str:
    if img[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if img[:4] == b"\x89PNG":
        return "image/png"
    if img[:4] in (b"RIFF",):
        return "image/webp"
    return "image/png"


def extraer_json(texto: str) -> dict:
    texto = re.sub(r"^```(?:json)?|```$", "", (texto or "").strip(), flags=re.M).strip()
    ini, fin = texto.find("{"), texto.rfind("}")
    if ini == -1 or fin == -1:
        raise ErrorIA("La respuesta de la IA no contiene JSON.")
    return json.loads(texto[ini: fin + 1])


def listar_modelos_ollama(host: str, api_key: str = "") -> list[str]:
    import requests

    headers = {"Authorization": f"Bearer {api_key.strip()}"} if api_key.strip() else {}
    r = requests.get(f"{host.strip().rstrip('/')}/api/tags", headers=headers, timeout=15)
    r.raise_for_status()
    return sorted(m.get("name") or m.get("model") for m in r.json().get("models", []))
