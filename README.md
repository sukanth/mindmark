<div align="center">

# 🔖 mindmark

**Your bookmarks, finally searchable.**\
Ask in natural language — mindmark remembers what you saved.

[![PyPI](https://img.shields.io/pypi/v/mindmark?color=blue&label=PyPI)](https://pypi.org/project/mindmark/)
[![Python](https://img.shields.io/pypi/pyversions/mindmark)](https://pypi.org/project/mindmark/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![CI](https://github.com/sukanth/mindmark/actions/workflows/ci.yml/badge.svg)](https://github.com/sukanth/mindmark/actions/workflows/ci.yml)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey)]()

100% local · No cloud · No API keys · Nothing leaves your machine

<img src="assets/mindmark-hero.gif" alt="mindmark demo" width="800" />

</div>

---

## Table of Contents

- [Features](#-features)
- [Prerequisites](#-prerequisites)
- [Install](#-install)
- [Quick Start](#-quick-start)
- [Usage](#-usage)
- [How It Works](#-how-it-works)
- [Storage Layout](#-storage-layout)
- [Uninstall](#-uninstall)
- [Development](#-development)
- [License](#-license)

---

## ✨ Features

| Command | What it does |
|---|---|
| `mindmark index <file>` | Parse an exported bookmarks HTML file, embed every bookmark locally, store vectors in SQLite |
| `mindmark find "query"` | Semantic search over titles, folders, domains, and URL slugs — returns top-K with similarity scores |
| `mindmark open "query"` | Search and open the best match in your default browser |
| `mindmark stats` | Show index size, model info, top domains, and top folders |

> 🔌 **Works offline** after the first run. Embeddings run on-device via [fastembed](https://github.com/qdrant/fastembed) (ONNX Runtime, ~130 MB one-time model download).

---

## 📋 Prerequisites

| Requirement | Details |
|---|---|
| **Python 3.9+** | [python.org/downloads](https://www.python.org/downloads/) — on Windows, check **"Add Python to PATH"** during setup |
| **pip** | Bundled with Python — verify with `pip --version` or `pip3 --version` |
| **Internet** | Needed only once to download the embedding model (~130 MB). Everything after that is offline |

<details>
<summary>💡 <strong>Windows tip — Python PATH</strong></summary>

If you installed Python from the **Microsoft Store**, `python` and `pip` are already on your PATH.\
If you installed from **python.org**, make sure you checked **"Add Python to PATH"** during setup.
</details>

---

## 📦 Install

### Recommended — pipx (isolated + globally on PATH)

```bash
pipx install mindmark
```

<details>
<summary>Don't have pipx?</summary>

```bash
pip install --user pipx && pipx ensurepath    # then restart your terminal
```

Or on macOS with Homebrew: `brew install pipx`
</details>

<details>
<summary>Alternative — pip with a virtual environment</summary>

**macOS / Linux:**

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install mindmark
```

**Windows (PowerShell):**

```powershell
python -m venv .venv; .venv\Scripts\Activate.ps1
pip install mindmark
```

**Windows (Command Prompt):**

```cmd
python -m venv .venv && .venv\Scripts\activate.bat
pip install mindmark
```
</details>

<details>
<summary>Editable install for development</summary>

```bash
git clone https://github.com/sukanth/mindmark.git
cd mindmark
pip install -e .[dev]
```
</details>

---

## ⚡ Quick Start

### 1️⃣ Export your bookmarks

| Browser | How |
|---|---|
| **Edge** | `edge://favorites` → `⋯` → **Export favorites** → save as HTML |
| **Chrome** | `chrome://bookmarks` → `⋮` → **Export bookmarks** → save as HTML |
| **Firefox** | `Ctrl+Shift+O` (`Cmd+Shift+O` on macOS) → **Import and Backup** → **Export Bookmarks to HTML** |

### 2️⃣ Build the index

```bash
# macOS / Linux
mindmark index ~/Downloads/bookmarks.html

# Windows (PowerShell)
mindmark index "$env:USERPROFILE\Downloads\bookmarks.html"
```

> First run downloads the embedding model (~130 MB) and caches it locally. Every run after that is instant and fully offline.

### 3️⃣ Search in natural language

<p align="center">
  <img src="assets/mindmark-find.gif" alt="mindmark find demo" width="800" />
</p>

```bash
mindmark find "python async tutorial"
mindmark find "react hooks best practices" -k 5
mindmark find "helm chart examples" --domain github.com
mindmark find "docker compose setup" --folder devops
```

### 4️⃣ Open a result directly

```bash
mindmark open "k8s cheat sheet"           # opens the best match
mindmark find "docker setup" --open 2     # opens result #2 from the list
```

<details>
<summary>💡 <strong>Tip — create a short alias</strong></summary>

**macOS / Linux** — add to `~/.bashrc` or `~/.zshrc`:

```bash
alias mm='mindmark open'
mm "docker setup"
```

**Windows** — add to your PowerShell `$PROFILE`:

```powershell
Set-Alias mm mindmark
mm open "docker setup"
```
</details>

### 5️⃣ JSON output for scripting

Pipe results into **fzf**, **jq**, **Alfred**, **Raycast**, **PowerToys Run**, or any tool that accepts JSON:

```bash
# macOS / Linux
mindmark find "istio service mesh" --json | jq '.[].url'

# Windows (PowerShell)
mindmark find "istio service mesh" --json | ConvertFrom-Json | ForEach-Object { $_.url }
```

---

## 📖 Usage

### Filters

Narrow down results without changing your query:

```bash
mindmark find "useful tools" --domain github.com     # only github.com results
mindmark find "useful tools" --folder work/kusto      # only bookmarks in matching folders
mindmark find "useful tools" -k 20                    # return top 20 instead of 10
```

### Re-indexing

Just rerun `mindmark index <file>`. It clears and rebuilds the index. The model is cached, so re-indexing 800+ bookmarks takes only seconds.

### Swap the embedding model

```bash
mindmark index bookmarks.html --model BAAI/bge-small-en-v1.5              # default, 384-dim
mindmark index bookmarks.html --model sentence-transformers/all-MiniLM-L6-v2
mindmark index bookmarks.html --model BAAI/bge-base-en-v1.5               # 768-dim, higher quality
```

Switching models triggers a full re-embed automatically. See the [fastembed supported models list](https://qdrant.github.io/fastembed/examples/Supported_Models/).

---

## 🧠 How It Works

```
Bookmarks HTML                                  "python async tutorial"
      │                                                  │
      ▼                                                  ▼
  ┌────────┐    ┌──────────┐    ┌──────────┐     ┌──────────┐
  │ Parse  │───▶│  Embed   │───▶│  Store   │     │  Embed   │
  │  HTML  │    │ (ONNX)   │    │ (SQLite) │◀────│  query   │
  └────────┘    └──────────┘    └──────────┘     └──────────┘
                                      │                │
                                      ▼                ▼
                                ┌──────────────────────────┐
                                │  Dot-product similarity  │
                                │   → top-K results        │
                                └──────────────────────────┘
```

1. **Parse** — A stateful tokenizer reads the Netscape bookmarks HTML and extracts every link with its full folder path.
2. **Embed** — Each bookmark becomes a rich text string (`title | folder | domain | path`) and is passed through a BGE/MiniLM ONNX model. Vectors are L2-normalized.
3. **Store** — Vectors live as `float32` blobs in a single SQLite file. For 800–10,000 bookmarks this is simpler than a vector DB and still sub-millisecond.
4. **Search** — Encode the query, compute dot products against all vectors, return the top-K.

---

## 🗂️ Storage Layout

| What | macOS / Linux | Windows | Override |
|---|---|---|---|
| Index database | `~/.mindmark/index.db` | `%LOCALAPPDATA%\mindmark\index.db` | `--db` flag or `MINDMARK_DB` env var |
| Home directory | `~/.mindmark/` | `%LOCALAPPDATA%\mindmark\` | `MINDMARK_HOME` env var |
| Embedding model | `~/.cache/fastembed/` | `%LOCALAPPDATA%\fastembed\` | Managed by fastembed |

---

## 🗑️ Uninstall

```bash
pipx uninstall mindmark    # if installed with pipx
pip uninstall mindmark      # if installed with pip
```

<details>
<summary>Remove stored data (optional)</summary>

The index and cached model are stored outside the package:

**macOS / Linux:**

```bash
rm -rf ~/.mindmark              # index database
rm -rf ~/.cache/fastembed        # cached embedding model (~130 MB)
```

**Windows (PowerShell):**

```powershell
Remove-Item -Recurse "$env:LOCALAPPDATA\mindmark"     # index database
Remove-Item -Recurse "$env:LOCALAPPDATA\fastembed"     # cached embedding model
```

> If you set a custom `MINDMARK_HOME`, remove that directory instead.
</details>

---

## 🛠️ Development

Contributions are welcome! See [CONTRIBUTING.md](CONTRIBUTING.md) for full details.

```bash
git clone https://github.com/sukanth/mindmark.git
cd mindmark
pip install -e .[dev]
pytest -q
```

<details>
<summary>Publishing to PyPI</summary>

### First-time setup

1. Create an account at [pypi.org](https://pypi.org/account/register/)
2. Generate an API token at [pypi.org/manage/account/token/](https://pypi.org/manage/account/token/)
3. Install build tools: `pip install build twine`

### Test on TestPyPI first (recommended)

```bash
python -m build
python -m twine upload --repository testpypi dist/*
pipx install --index-url https://test.pypi.org/simple/ mindmark
```

### Publish to PyPI

```bash
python -m build
python -m twine upload dist/*
```

Use `__token__` as the username when prompted.
</details>

<details>
<summary>Alternative distribution methods</summary>

### GitHub release

```bash
python -m build
gh release create v0.1.0 dist/*
# Users install:
pipx install https://github.com/sukanth/mindmark/releases/download/v0.1.0/mindmark-0.1.0-py3-none-any.whl
```

### Standalone executable (no Python required)

```bash
pip install pyinstaller
pyinstaller --onefile -n mindmark -p src src/mindmark/__main__.py
# Creates: dist/mindmark (macOS/Linux) or dist/mindmark.exe (Windows)
```

### Docker

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY . .
RUN pip install --no-cache-dir .
ENTRYPOINT ["mindmark"]
```

```bash
docker build -t mindmark .
docker run --rm -v $HOME/.mindmark:/root/.mindmark \
    -v $HOME/Downloads:/downloads mindmark \
    index /downloads/bookmarks.html
```
</details>

---

## 📄 License

MIT — see [LICENSE](LICENSE).
