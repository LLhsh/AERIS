# AERIS


## Features

- Extract text from PDF and DOCX documents.
- Configure model names, prompts, API endpoints and optional authorization headers.
- Extract technical parameters as JSON and requirements as hierarchical XML.
- Convert requirement XML to XMI containing UML classes and SysML requirement elements.
- Split long documents, process chunks sequentially, save results, retry processing failures once and record errors.
- Merge user-selected requirement files and regenerate hierarchical identifiers.
- Display structured tables, requirement trees, source text and model output.
- Fill Word parameters from Excel, insert tables and images, and convert Word sections to template-based PowerPoint slides.

## Source layout

| Directory | Purpose |
| --- | --- |
| `ui/` | PySide2 desktop interface and workflow integration |
| `workers/` | Background document parsing and model requests |
| `utils/` | File handling, API configuration, JSON cleanup and XML/XMI conversion |
| `batch_processing/` | Sequential chunk processing and error handling |
| `word_to_ppt/` | Word-to-PowerPoint conversion |

`main.py` is the desktop entry point. `mock_api_server.py` is a synthetic API server for interface testing, not a model inference server. Its default token is an explicitly public demonstration value; use `--token` to override it.

## Dependencies and integration

The source imports PySide2, requests, PyPDF2, python-docx, pandas, Pillow and python-pptx. Excel support additionally depends on an appropriate pandas engine, such as openpyxl for XLSX or xlrd for XLS. Use a Python version supported by PySide2; a validated, pinned environment is not included in this source snapshot.

**An external dependency is required:** `ui/doc_analysis_tab.py` imports `data.xml_to_reqif_converter.XMLToReqIFConverter`. This module is not included in this repository and must be supplied before the current desktop entry point can start. ReqIF export has not been independently validated from this snapshot.

Configure the actual model endpoint and model name in the desktop settings. For a direct Ollama native chat connection, use `/api/chat`; the OpenAI-compatible chat path is `/v1/chat/completions`. The source's default `/v1/chat/completion` is a custom proxy/mock route, not the standard Ollama route. The connection-test button currently requests `deepseek-r1:70b`; adjust it if the server hosts a different model.

The desktop model list stores names for API requests; it does not download or deploy model weights. A default model name does not establish that a particular GPU can host it. Document requests currently specify a 16,384-token context, and chat requests specify 65,536 tokens; review these settings against available GPU memory before use.
