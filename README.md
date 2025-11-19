# FX-Translator

**PDF Layout Analysis and AI Translation Tool with Intelligent Segmentation**

🤖 Powered by HURIDOCS, LayoutLMv3 & LM Studio  
🔒 100% Local Processing - No Cloud Data Transfer

---

## 📋 Overview

FX-Translator is an advanced PDF document processing tool that:
- Automatically detects document structure (headings, paragraphs, tables)
- Intelligently segments text blocks
- Translates content using local LLM models
- Exports results to DOCX and annotated PDF

### Key Features

- **🎯 Smart Layout Analysis** — Three PDF structure analysis modes:
  - HURIDOCS (Docker service with GPU)
  - LayoutLMv3 (Built-in Transformers model)
  - PyMuPDF (Fast extraction without ML)

- **🧩 Intelligent Segmentation**
  - Automatic text block detection and merging
  - Element type classification (headings, paragraphs, captions)
  - Reading order sorting

- **📖 Spread Processing**
  - Automatic two-page spread detection
  - Split spreads into separate logical pages
  - Forced half-split mode

- **🔄 Deglue Operations**
  - Smart separation of merged text blocks
  - PDF-aware analysis for precise splitting

- **🤖 AI Translation**
  - LM Studio integration for local translation
  - Support for any local LLM models
  - Batch processing for speed optimization

- **📝 Export Results**
  - **DOCX** — Side-by-side original and translation table
  - **PDF** — Annotated document with translation comments
  
- **📊 Metrics & Logging**
  - Detailed processing statistics
  - Execution time tracking for each stage

---

## 🚀 Quick Start

### Prerequisites

1. **Python 3.9+**
2. **Docker** (for HURIDOCS) or **GPU** (for LayoutLMv3)
3. **LM Studio** with running local LLM

### Installation

```bash
# Clone repository
git clone https://github.com/Mike-voyager/FX-anotator-ai-translator.git
cd FX-anotator-ai-translator

# Create virtual environment
python -m venv .venv311
.venv311\\Scripts\\activate  # Windows
# source .venv311/bin/activate  # Linux/Mac

# Install dependencies
pip install -r requirements.txt

# Optional: PyTorch with CUDA for LayoutLMv3
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
```

### Start HURIDOCS (Docker)

```bash
# Run container with GPU
docker run --rm --name pdf-document-layout-analysis \\
    --gpus '"device=0"' \\
    -p 5060:5060 \\
    --entrypoint ./start.sh \\
    huridocs/pdf-document-layout-analysis:v0.0.31
```

### Configuration

Copy `.env.example` to `.env` and configure:

```env
# HURIDOCS API
HURIDOCS_BASE=http://localhost:5060

# LM Studio API
LMS_BASE=http://127.0.0.1:5555/v1
LMSTUDIO_MODEL=your-model-name

# Processing options
TIMEOUT=600
```

---

## 💻 Usage

### API Mode (Recommended)

```python
from fx_translator.processing.pipeline import run_pipeline

run_pipeline(
    input_pdf="input.pdf",
    out_pdf_annotated="output_annotated.pdf",
    out_docx="output.docx",
    src_lang="en",
    tgt_lang="ru",
)
```

### GUI Mode

```bash
python main.py
```

### Advanced Options

#### Page Range Processing

```python
run_pipeline(
    input_pdf="document.pdf",
    out_pdf_annotated="annotated.pdf",
    out_docx="translation.docx",
    src_lang="en",
    tgt_lang="ru",
    start_page=10,      # Start from page 10
    end_page=20,        # End at page 20
)
```

#### Spread Processing

```python
run_pipeline(
    input_pdf="document.pdf",
    out_pdf_annotated="annotated.pdf",
    out_docx="translation.docx",
    src_lang="en",
    tgt_lang="ru",
    split_spreads_enabled=True,      # Enable spread splitting
    force_split_spreads=True,        # Force half-split
    force_split_exceptions="1,3-5",  # Exceptions (pages without splitting)
)
```

#### Page-by-Page Processing (Transactional Mode)

```python
from fx_translator.processing.pipeline import run_pipeline_transactional

run_pipeline_transactional(
    input_pdf="document.pdf",
    out_pdf_annotated="annotated.pdf",
    out_docx="translation.docx",
    src_lang="it",
    tgt_lang="ru",
    restart_every=20,  # Restart container every 20 pages
    start_page=1,
    end_page=50,
)
```

#### PyMuPDF Mode (Without HURIDOCS)

```python
from fx_translator.processing.pipeline import run_pipeline_pymupdf

run_pipeline_pymupdf(
    input_pdf="document.pdf",
    out_pdf_annotated="annotated.pdf",
    out_docx="translation.docx",
    src_lang="en",
    tgt_lang="ru",
    use_llm_grouping=False,  # Optional LLM block grouping
)
```

#### LayoutLMv3 Mode (Built-in ML Model)

```python
from fx_translator.processing.pipeline import run_pipeline_layoutlmv3

run_pipeline_layoutlmv3(
    input_pdf="document.pdf",
    out_pdf_annotated="annotated.pdf",
    out_docx="translation.docx",
    src_lang="it",
    tgt_lang="ru",
    use_gpu=True,    # Use GPU
    dpi=200,         # DPI for page conversion
)
```

---

## 📦 Project Structure

```
FX-anotator-ai-translator/
├── fx_translator/              # Main package
│   ├── core/                  # Core models and configuration
│   │   ├── models.py         # Data models (Segment, PageBatch)
│   │   ├── config.py         # Settings from .env
│   │   ├── types.py          # Type aliases
│   │   └── exceptions.py     # Custom exceptions
│   │
│   ├── api/                   # External service integrations
│   │   ├── huridocs.py       # HURIDOCS API client
│   │   ├── layoutlmv3.py     # LayoutLMv3 analyzer
│   │   └── lmstudio.py       # LM Studio API client
│   │
│   ├── processing/            # Processing pipelines
│   │   ├── pipeline.py       # Main pipelines
│   │   ├── analyzers/        # Layout and segment analyzers
│   │   │   ├── layout.py    # Spread processing
│   │   │   └── segments.py  # Refinement and deglue
│   │   └── extractors/       # Text extractors
│   │       └── pymupdf.py   # PyMuPDF extractor
│   │
│   ├── export/                # Result export
│   │   ├── docx.py           # DOCX generation
│   │   └── pdf.py            # PDF annotation
│   │
│   ├── utils/                 # Utilities
│   │   ├── text.py           # Text processing
│   │   ├── geometry.py       # Geometric operations
│   │   └── metrics.py        # Metrics and timers
│   │
│   ├── orchestration/         # Docker management (optional)
│   │   └── docker_manager.py
│   │
│   └── gui/                   # Tkinter GUI (optional)
│       └── app.py
│
├── main.py                    # Entry point
├── requirements.txt           # Dependencies
├── pyproject.toml            # Project configuration
├── .env.example              # Configuration example
└── dev.ps1                   # Development script (Windows)
```

---

## 🔧 Development

### Install Dev Dependencies

```bash
# Windows
.\\dev.ps1 install-dev

# Linux/Mac
pip install -r requirements.txt
```

### Development Tools

```bash
# Format code
.\\dev.ps1 format         # black fx_translator/ main.py

# Type checking
.\\dev.ps1 mypy           # mypy fx_translator/

# Check formatting
.\\dev.ps1 check          # black --check

# All checks
.\\dev.ps1 lint

# Clean cache
.\\dev.ps1 clean
```

### Linter Configuration

Project uses:
- **Black** for formatting (line-length=88)
- **Mypy** for type checking (strict mode)
- Full type hints support

---

## 🎯 Architecture

### Modular Design

- **Clear separation of concerns** — Each module has a single responsibility
- **Type hints** — Full typing support for IDE autocomplete
- **Error handling** — Comprehensive exception system
- **Logging** — Detailed logs with metrics

### Key Modules

- **core/** — Data models, configuration, types
- **processing/** — Main pipeline with analyzers
- **api/** — External service integrations
- **export/** — Multiple output format support

### Four Processing Pipelines

1. **run_pipeline()** — Standard HURIDOCS pipeline
   - Analyzes entire document in one request
   - Optimal for stable documents

2. **run_pipeline_transactional()** — Page-by-page pipeline
   - Processes each page separately
   - Automatic restart on failures
   - Fault tolerance

3. **run_pipeline_pymupdf()** — No external dependencies
   - Uses only PyMuPDF
   - Fast processing without ML
   - Optional LLM grouping

4. **run_pipeline_layoutlmv3()** — Built-in ML model
   - Local Transformers model
   - No Docker required
   - GPU acceleration

---

## 📝 Known Behaviors

### Deglue Operations

Deglue operations may work unpredictably in some cases. This is normal and related to heuristic algorithms for separating merged blocks.

### Spread Processing

Automatic spread detection works based on page width heuristics. For complex cases, forced splitting with exceptions is recommended.

---

## 🤝 Contributing

Project is open for improvements and suggestions. Main directions:

- Segmentation algorithm improvements
- New export formats
- Performance optimization
- Extended language support

---

## 📄 License

MIT License

---

## 👤 Author

**Mike-voyager**

GitHub: [Mike-voyager/FX-anotator-ai-translator](https://github.com/Mike-voyager/FX-anotator-ai-translator)

---

## 🙏 Acknowledgments

- **HURIDOCS** — PDF layout analysis
- **Microsoft LayoutLMv3** — Document understanding model
- **LM Studio** — Local LLM inference
- **PyMuPDF** — PDF processing library
- **python-docx** — DOCX generation

---

## 📮 Support

For questions and bug reports, use [GitHub Issues](https://github.com/Mike-voyager/FX-anotator-ai-translator/issues)