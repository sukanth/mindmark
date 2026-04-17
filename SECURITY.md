# Security Policy

## Supported versions

| Version | Supported |
|---------|-----------|
| 0.1.x   | ✅        |

## Reporting a vulnerability

If you discover a security vulnerability, please **do not** open a public issue.

Instead, email **contact.sukanth@gmail.com** with:

- A description of the vulnerability
- Steps to reproduce
- Any potential impact

You should receive an acknowledgment within 48 hours. We will work with you to understand and address the issue before any public disclosure.

## Scope

mindmark runs entirely on your local machine. The main security considerations are:

- **SQLite database** — stored at `~/.mindmark/index.db` with user-level permissions
- **Bookmark data** — parsed from your exported HTML file, never transmitted externally
- **Embedding model** — downloaded once from Hugging Face via fastembed; no data is sent upstream
