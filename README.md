# FX-Translator

**PDF annotation and AI translation tool with intelligent layout analysis**

🤖 Powered by HURIDOCS & LM Studio    
🔒 100% local processing

---

## ✨ Features

- 📄 **Smart PDF Analysis** — HURIDOCS-powered layout detection
- 🧩 **Intelligent Segmentation** — Automatic text block detection and merging
- 📖 **Spread Detection** — Automatic detection and splitting of two-page spreads
- 🔄 **Deglue Operations** — Smart separation of merged text blocks (may work unpredictably)
- 🤖 **AI Translation** — LM Studio integration with any local LLM
- 📝 **DOCX Export** — Side-by-side original and translation tables
- 🎨 **Annotated PDF** — Visual markup with segment IDs and types
- 📊 **Metrics & Logging** — Comprehensive processing statistics

---

## 🚀 Quick Start

### Prerequisites

1. **Python 3.9+**
2. **HURIDOCS PDF Segmenter** (Docker):
   ```bash
   docker run -p 5060:5060 huridocs/pdf-segmenter
   ```
3. **LM Studio** running at `http://localhost:5555/v1`

### Installation

```bash
git clone https://github.com/Mike-voyager/FX-anotator-ai-translator.git
cd FX-anotator-ai-translator
pip install -r requirements.txt
```

### Usage

#### API Mode (Recommended)

```python
from fx_translator.processing.pipeline import run_pipeline

run_pipeline(
    inputpdf="input.pdf",
    outpdfannotated="output_annotated.pdf",
    outdocx="output.docx",
    srclang="en",
    tgtlang="ru",
)
```

#### GUI Mode (if available)

```bash
python main.py
```

---

## 📦 Project Structure

```
FX-anotator-ai-translator/
├── fx_translator/
│   ├── core/              # Models, types, config, exceptions
│   ├── utils/             # Text, geometry, JSON utilities
│   ├── api/               # HURIDOCS & LM Studio clients
│   ├── processing/        # PDF processing pipeline
│   │   ├── analyzers/     # Layout & segment analysis
│   │   └── extractors/    # Text extraction (optional)
│   ├── export/            # DOCX & PDF export
│   ├── orchestration/     # Docker management (optional)
│   └── gui/               # Tkinter GUI (optional)
├── main.py                # Entry point
├── requirements.txt       # Dependencies
└── pyproject.toml         # Project config
```

---

## 🛠️ Configuration

Copy `.env.example` to `.env` and configure:

```env
HURIDOCS_BASE=http://localhost:5060
LMS_BASE=http://127.0.0.1:5555/v1
LMS_MODEL=your-model-name
```

---

## 📖 Advanced Usage

### Custom Pipeline

```python
from fx_translator.processing.pipeline import run_pipeline

run_pipeline(
    inputpdf="document.pdf",
    outpdfannotated="annotated.pdf",
    outdocx="translation.docx",
    srclang="en",
    tgtlang="ru",
    startpage=10,        # Start from page 10
    endpage=20,          # End at page 20
    splitspreads_enabled=True,  # Split two-page spreads
    pausems=1000,        # 1 second pause between pages
)
```

### Direct API Usage

```python
from fx_translator.api.huridocs import huridocs_analyze_pdf
from fx_translator.api.lmstudio import lmstudio_translate_simple
from fx_translator.processing.analyzers.segments import refine_huridocs_segments
from fx_translator.processing.analyzers.layout import split_spreads
from fx_translator.export.docx import export_docx
from fx_translator.export.pdf import annotate_pdf_with_segments

# Your custom pipeline here...
```

---

## 🔧 Development

### Install Dev Dependencies

```bash
pip install -e ".[dev]"
```

### Code Quality

```bash
# Format code
black fx_translator/

# Type checking
mypy fx_translator/

# Run tests (when available)
pytest
```

---

## 📊 Technical Details

### Architecture

- **Modular design** — Clean separation of concerns
- **Type hints** — Full typing support for IDE autocomplete
- **Error handling** — Comprehensive exception handling
- **Logging** — Detailed processing logs with metrics

### Key Modules

- **core/** — Data models, configuration, type definitions
- **processing/** — Main pipeline with analyzers
- **api/** — External service integrations
- **export/** — Multiple output format support

---

## 📝 License

MIT License

---

## 👤 Author

**Mike-voyager**

---

## 🙏 Acknowledgments

- [HURIDOCS](https://huridocs.org/) — PDF layout analysis
- [LM Studio](https://lmstudio.ai/) — Local LLM inference
- [PyMuPDF](https://pymupdf.readthedocs.io/) — PDF processing
- [python-docx](https://python-docx.readthedocs.io/) — DOCX generation

---

## 📮 Support

For issues and questions, please use the [GitHub Issues](https://github.com/Mike-voyager/FX-anotator-ai-translator/issues) page.
