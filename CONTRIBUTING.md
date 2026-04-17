# Contributing to mindmark

Thanks for your interest in contributing! This guide will help you get started.

## Development setup

```bash
git clone https://github.com/sukanth/mindmark.git
cd mindmark
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
python -m pip install -e ".[dev]"
```

## Running tests

```bash
pytest -q
```

## How to contribute

### Reporting bugs

Open an [issue](https://github.com/sukanth/mindmark/issues/new?template=bug_report.md) with:

- Steps to reproduce
- Expected vs. actual behavior
- Python version and OS

### Suggesting features

Open an [issue](https://github.com/sukanth/mindmark/issues/new?template=feature_request.md) describing the use case and proposed solution.

### Submitting a pull request

1. Fork the repo and create a branch from `master`.
2. Make your changes (add tests if applicable).
3. Run `pytest -q` to verify nothing is broken.
4. Open a PR with a clear description of what you changed and why.

### Code style

- Follow [PEP 8](https://peps.python.org/pep-0008/).
- Use type hints where practical.
- Keep functions focused and well-named — minimal comments, clear code.

### Commit messages

Use clear, imperative-mood messages:

```
Add --format flag to find command
Fix folder filter case sensitivity
```

## Project structure

```
src/mindmark/
├── __init__.py     # Package initialisation
├── __main__.py     # Entry point for `python -m mindmark`
├── cli.py          # CLI entry point (argparse)
├── index.py        # Indexing logic
└── parser.py       # Bookmark / document parser
```

## Questions?

Open an [issue](https://github.com/sukanth/mindmark/issues) or reach out via an issue. We're happy to help!
