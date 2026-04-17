# mindmark

> **Your bookmarks, finally searchable.** Ask in natural language; mindmark remembers what you saved.

**100% local.** No cloud, no API keys, nothing leaves your machine. Embeddings run on-device via [fastembed](https://github.com/qdrant/fastembed) (ONNX, ~130 MB one-time model download).

---

## What it does

- **`mindmark index <file>`** — parse an exported Netscape bookmarks HTML file, embed every bookmark locally, and store vectors in SQLite.
- **`mindmark find "natural-language query"`** — semantic search over titles, folder paths, domains, and URL slugs. Returns top-K with cosine-similarity scores.
- **`mindmark open "query"`** — open the top result in your default browser.
- **`mindmark stats`** — show index size, model used, top domains, and top folders.

Works offline after the first index run (model cached locally by fastembed).

---

## Install

Requires **Python 3.9+**.

### Option 1 — pipx (recommended, isolated + globally on PATH)

```bash
pipx install mindmark
```

### Option 2 — regular pip / venv

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install .
```

### Option 3 — editable install for development

```bash
pip install -e .[dev]
```

---

## Quick start

### 1. Export your bookmarks

- **Edge** — `edge://favorites` → `⋯` → **Export favorites** → save HTML
- **Chrome** — `chrome://bookmarks` → `⋮` → **Export bookmarks** → save HTML
- **Firefox** — `Ctrl+Shift+O` → **Import and Backup** → **Export Bookmarks to HTML**

### 2. Build the index

```bash
mindmark index ~/Downloads/bookmarks.html
```

First run downloads the embedding model (~130 MB) to `~/.cache/fastembed` (or `%LOCALAPPDATA%\fastembed` on Windows). Subsequent runs are offline.

### 3. Search in natural language

```bash
mindmark find "python async tutorial"
mindmark find "react hooks best practices" -k 5
mindmark find "helm chart examples" --domain github.com
mindmark find "docker compose setup" --folder devops
```

### 4. Open a result directly

```bash
mindmark open "k8s cheat sheet"           # opens the best match
mindmark find "docker setup" --open 2     # opens result #2 from the list
```

Tip: alias it to something even shorter.

```bash
alias mm='mindmark open'
mm "docker setup"
```

### 5. JSON for scripting / fzf / Alfred / Raycast

```bash
mindmark find "istio service mesh" --json | jq '.[].url'
```

---

## Re-indexing

Just rerun `mindmark index <file>`. It clears and rebuilds the `bookmarks` table. The model download is cached, so re-indexing 800 bookmarks takes seconds after the first time.

## Storage layout

| What | Where | Notes |
|---|---|---|
| SQLite index | `~/.mindmark/index.db` | override with `--db` or `MINDMARK_DB` |
| Alternate home dir | `~/.mindmark/` | override with `MINDMARK_HOME` |
| Embedding model | `~/.cache/fastembed/` | managed by fastembed |

## Filters

- `--domain github.com` — only results whose domain contains `github.com`
- `--folder work/kusto` — only results inside folder paths containing `work/kusto`
- `-k 20` — return top 20 instead of top 10

## Swap the embedding model

```bash
mindmark index bookmarks.html --model BAAI/bge-small-en-v1.5       # default, 384-dim
mindmark index bookmarks.html --model sentence-transformers/all-MiniLM-L6-v2
mindmark index bookmarks.html --model BAAI/bge-base-en-v1.5        # 768-dim, higher quality, slower
```

Switching models triggers a full re-embed automatically. See the [fastembed supported models list](https://qdrant.github.io/fastembed/examples/Supported_Models/).

---

## How it works

1. **Parse** — a small stateful tokenizer reads the Netscape bookmarks HTML and extracts every `<A>` with its ancestor `<H3>` folder stack, so each bookmark knows its full folder path.
2. **Embed** — each bookmark becomes the string `title | folder: Dev/Tools | domain: github.com | path: docs setup guide` and is passed through a BGE/MiniLM ONNX model. Vectors are L2-normalized so cosine similarity = dot product.
3. **Store** — vectors live as `float32` BLOBs in a single SQLite file. For 800–10,000 bookmarks this is dramatically simpler than a vector DB and still sub-millisecond.
4. **Search** — encode the query, take the dot product against all vectors, return the top-K.

---

## Publishing to PyPI

### First-time setup

1. Create an account at [pypi.org](https://pypi.org/account/register/)
2. Generate an API token at [pypi.org/manage/account/token/](https://pypi.org/manage/account/token/)
3. Install the build tools:

```bash
pip install build twine
```

### Test on TestPyPI first (recommended)

```bash
python -m build
python -m twine upload --repository testpypi dist/*
# verify it works:
pipx install --index-url https://test.pypi.org/simple/ mindmark
```

### Publish to PyPI

```bash
python -m build
python -m twine upload dist/*
```

Twine will prompt for your API token (use `__token__` as the username). After uploading, anyone can install with:

```bash
pipx install mindmark
```

### Alternative distribution methods

<details>
<summary>GitHub release + pipx</summary>

```bash
python -m build
gh release create v0.1.0 dist/*

# Users install:
pipx install https://github.com/sukanth/mindmark/releases/download/v0.1.0/mindmark-0.1.0-py3-none-any.whl
```
</details>

<details>
<summary>Standalone executable (no Python required)</summary>

```bash
pip install pyinstaller
pyinstaller --onefile -n mindmark -p src src/mindmark/__main__.py
# dist/mindmark (macOS/Linux) or dist/mindmark.exe (Windows)
```

Ship the binary in a GitHub release. First launch still downloads the ONNX model (~130 MB).
</details>

<details>
<summary>Docker</summary>

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

## Tests

```bash
pip install -e .[dev]
pytest -q
```

## License

MIT
