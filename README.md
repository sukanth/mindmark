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
pipx install .
# or, after publishing to PyPI:
# pipx install mindmark
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
mindmark find "how do I get access to kusto clusters"
mindmark find "visa stamping appointment" -k 5
mindmark find "helm chart examples" --domain github.com
mindmark find "safefly approval guide" --folder microsoft
```

### 4. Open a result directly

```bash
mindmark open "k8s cheat sheet"           # opens the best match
mindmark find "kusto access" --open 2     # opens result #2 from the list
```

Tip: alias it to something even shorter.

```bash
alias mm='mindmark open'
mm "kusto access"
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
2. **Embed** — each bookmark becomes the string `title | folder: Work/Kusto | domain: eng.ms | path: docs kusto access` and is passed through a BGE/MiniLM ONNX model. Vectors are L2-normalized so cosine similarity = dot product.
3. **Store** — vectors live as `float32` BLOBs in a single SQLite file. For 800–10,000 bookmarks this is dramatically simpler than a vector DB and still sub-millisecond.
4. **Search** — encode the query, take the dot product against all vectors, return the top-K.

---

## Distribute it

Pick one based on your audience:

### A. GitHub release + pipx (easiest for individual users)

```bash
# Developer publishes:
python -m pip install build
python -m build           # creates dist/mindmark-0.1.0-py3-none-any.whl
gh release create v0.1.0 dist/*

# Users install:
pipx install https://github.com/<you>/mindmark/releases/download/v0.1.0/mindmark-0.1.0-py3-none-any.whl
```

### B. Publish to PyPI

```bash
python -m pip install build twine
python -m build
python -m twine upload dist/*
# then anyone can run:
pipx install mindmark
```

### C. Single-file standalone executable (no Python required)

```bash
pip install pyinstaller
pyinstaller --onefile -n mindmark -p src src/mindmark/__main__.py
# dist/mindmark.exe  (Windows)  or  dist/mindmark  (macOS/Linux)
```

Ship the resulting binary in a GitHub release. First launch still needs internet to download the ONNX model (or pre-bundle the model directory under `~/.cache/fastembed`).

### D. Docker (for servers / teammates without local Python)

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

### E. Internal Microsoft distribution

- Publish the wheel to an internal Azure Artifacts feed, then `pipx install mindmark --index-url <feed>`.
- Or check `dist/*.whl` into an internal repo and point colleagues at `pipx install <url-to-wheel>`.

---

## Tests

```bash
pip install -e .[dev]
pytest -q
```

## License

MIT
