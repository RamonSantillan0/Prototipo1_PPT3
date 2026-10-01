# Entidad · Sistema de Reclamos (prototipo)

Prototipo genérico para una entidad reguladora de servicios públicos (la **Entidad**) que recibe reclamos de
usuarios contra el **ente distribuidor de energía**: dashboard de reclamos, consulta normativa con RAG y chatbot
de recepción de reclamos. Parte del dashboard de `Hito3_PPt2`.

## Instalación

```bat
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

O doble clic en `instalar.bat` (la primera vez) y después en `iniciar.bat`.

## Páginas

| Página | Qué muestra |
|---|---|
| 📊 **Dashboard** | Indicadores de reclamos con datos de ejemplo o con un dataset propio (reclamos.csv). |
| 📚 **Consulta normativa (RAG)** | Chat que responde con la base de conocimiento de la Entidad (normativa, modelos de resolución y dictamen, códigos, circuito y plazos, indicadores) y **cita las fuentes**. Pestañas: **Documentos** (subir PDF/Word/TXT arrastrando y soltando, editar título/fecha/vigencia, quitar, activar la búsqueda por significado y reindexar), **Opiniones** (👍/👎 de cada respuesta) y **Cómo funciona**. |
| 💬 **Recepción de reclamos (chatbot)** | Simula la Mesa de entrada: el usuario cuenta el problema, el bot propone el código (F-16, S-10, O-03…), pide los datos que faltan, muestra el resumen y registra el expediente con área de derivación, circuito y fechas estimadas. Constancia y CSV descargables. |

## IA opcional

En la barra lateral de las páginas de consulta y recepción: **Usar IA** + API key de Ollama Cloud (o Claude).

- **Sin IA** (por defecto): funciona sin internet. El RAG muestra el fragmento más relevante y las fuentes; el
  chatbot clasifica por palabras clave.
- **Con IA**: el RAG redacta la respuesta citando `[1]`, `[2]`; el chatbot clasifica el reclamo con la IA.
- **Privacidad**: los datos personales (nombre, DNI, suministro, domicilio, teléfono) se detectan en la PC y se
  reemplazan por marcadores (`{{USUARIO}}`, `{{DOMICILIO}}`…) antes de enviar cualquier texto.

La key también puede ir en `.streamlit\secrets.toml`:

```toml
OLLAMA_API_KEY = "..."
```

## Estructura

```
app.py                      # configuración, estilos y menú de páginas
paginas/                    # dashboard.py · consulta_normativa.py · recepcion.py
components/ · data/         # gráficos y datos del dashboard
asistente/
├── rag.py · indice.py · fragmentos.py · textos.py   # RAG (búsqueda BM25 + respuesta con citas)
├── recepcion.py            # lógica del chatbot: clasificación, datos, circuito y plazos
├── llm.py · seudonimizador.py · ui.py · config.py
conocimiento/
├── corpus/                 # documentos de la base de conocimiento
└── indice/                 # índice ya armado; «Reindexar» en la página de consulta
```

Para sumar documentos: en **Consulta normativa → Documentos**, arrastrar los archivos y apretar **Guardar** (se
reindexa solo). Los quitados van a `conocimiento/corpus/_archivados/`.

### Búsqueda por significado (opcional)

Por defecto la búsqueda es por palabras clave. Para que también encuentre por significado («¿quién firma?» →
«EL DIRECTORIO…»): instalar [Ollama](https://ollama.com), ejecutar `ollama pull bge-m3` y en **Documentos → Búsqueda
por significado** elegir *Ollama* y **Reindexar**. Se calcula en la PC; los documentos no salen de la computadora.
Si Ollama no está abierto, la consulta avisa y sigue funcionando solo con palabras clave.

### Opiniones

Los 👍/👎 se guardan en `opiniones/feedback.csv` (no se sube a git: las preguntas pueden tener datos personales).

## Datos

El dashboard usa datos de ejemplo generados al azar. Los datos reales (`muestra_limpia`, archivos `.csv`) **no se
suben al repositorio** porque contienen nombres y domicilios de reclamantes (ver `.gitignore`); se cargan desde la
app con «Cargar dataset propio».

## Límites del prototipo

- Los reclamos registrados por el chatbot viven solo en la sesión (se descargan como CSV); no se guardan en ningún sistema.
- El número de expediente es simulado; las fechas suman días hábiles sin feriados.
- El área de derivación por código es una propuesta (técnica para S, M y daños; comercial para F; jurídica para fraude).
# Prototipo1_PPT3
