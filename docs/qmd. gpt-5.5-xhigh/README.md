# QMD v2.1.0 Research Summary

## Run metadata

- Agent slug: `gpt-5.5-xhigh`
- Agent: Codex using gpt-5.5, reasoning effort xhigh (from Codex session turn_context).
- Subject: `tobi/qmd`
- Pinned tag: `v2.1.0`
- Pinned commit: `65cd1b3fd02891d1ee0eefa751620918664fa321`
- Submodule path: `research/qmd/`
- Scope: static review only. No upstream code, tests, scripts, examples, package managers, CLIs, build steps, or services were executed.
- Report date: 2026-05-06

All QMD-specific evidence below refers to `research/qmd/` at commit `65cd1b3fd02891d1ee0eefa751620918664fa321`.

## Verdict matrix

| Area                   | Verdict                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      |
| ---------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Overall recommendation | **Reject** as the core downstream indexing substrate. QMD is a strong local markdown/code search tool, but it is not a heterogeneous-source, multimodal indexing framework.                                                                                                                                                                                                                                                                                                                                                  |
| Sparkle fit            | **Low-medium**. Sparkle labels can be encoded as collection names, path prefixes, or context strings, but QMD has no first-class S/P/A/R/K/L/E taxonomy, no typed source connectors, no permission/owner model, and no conflict state. Collections and contexts are plain YAML/SQLite fields (`research/qmd/src/collections.ts:27`, `research/qmd/src/store.ts:803` @ `65cd1b3...`).                                                                                                                                         |
| Multimodal fit         | **Low**. QMD reads indexed files as UTF-8 text and defaults to markdown globbing (`research/qmd/src/store.ts:45`, `research/qmd/src/store.ts:1211` @ `65cd1b3...`). Code files receive optional AST-aware text chunking, but images, audio, and video have no native extraction, embedding, or retrieval path.                                                                                                                                                                                                               |
| Security posture       | **Mixed-negative for product embedding**. The local-only design reduces exposure, and FTS input is sanitized/prepared, but the HTTP/MCP surface has no authentication, the index is plaintext SQLite, model downloads are not pinned by immutable digest, config can execute shell commands during update, and contexts can be injected into MCP instructions (`research/qmd/src/mcp/server.ts:637`, `research/qmd/src/cli/qmd.ts:554`, `research/qmd/src/llm.ts:239`, `research/qmd/src/mcp/server.ts:101` @ `65cd1b3...`). |
| Extensibility          | **Medium for text search, low for source/modality expansion**. The v2 SDK exposes search, retrieval, collection/context management, update, embed, and lifecycle methods (`research/qmd/src/index.ts:216`, `research/qmd/src/index.ts:338` @ `65cd1b3...`), and model URIs are configurable (`research/qmd/src/llm.ts:438` @ `65cd1b3...`). There is no stable connector/plugin interface beyond filesystem collections, YAML config, SDK calls, and MCP tools.                                                              |
| Adoption effort        | **High**. Product adoption would require a wrapper or fork for source identity, permissions, Sparkle schema, connector sync, native multimodal pipelines, hardened HTTP auth, encrypted storage, and model provenance controls.                                                                                                                                                                                                                                                                                              |

## Report links

- [Architecture](architecture.md)
- [Security](security.md)
- [Applicability](applicability.md)

## Executive summary

QMD v2.1.0 is a local TypeScript/Bun/Node package for indexing markdown and related text files into SQLite, searching with SQLite FTS5 BM25, `sqlite-vec` vector search, local GGUF embeddings, local query expansion, and local reranking. The upstream README describes it as an on-device search engine for markdown notes, transcripts, documentation, and knowledge bases, combining BM25, vector semantic search, and LLM reranking (`research/qmd/README.md:1`, `research/qmd/README.md:3`, `research/qmd/README.md:5` @ `65cd1b3...`). Its package exposes a `qmd` CLI and a library export (`research/qmd/package.json:6`, `research/qmd/package.json:14` @ `65cd1b3...`), and the README documents MCP tools for query, get, multi_get, and status (`research/qmd/README.md:72`, `research/qmd/README.md:76` @ `65cd1b3...`).

The architecture is coherent for personal/local text retrieval: collections define directories and glob patterns, indexing stores content-addressed documents in SQLite, FTS triggers maintain a full-text index, embedding generates chunk vectors, and query combines BM25, vector search, reciprocal rank fusion, and reranking (`research/qmd/src/collections.ts:27`, `research/qmd/src/store.ts:746`, `research/qmd/src/store.ts:824`, `research/qmd/src/store.ts:1397`, `research/qmd/src/store.ts:3893` @ `65cd1b3...`). This makes QMD useful as a reference implementation for compact local markdown search and agent-facing retrieval UX.

It does not satisfy the repository goals as a primary substrate. For Sparkle, QMD preserves collection name, normalized path, title, content hash, modified timestamps, context strings, and active/inactive state, but it lacks typed source identity, ownership, permissions, sync conflicts, or a schema that can enforce S/P/A/R/K/L/E distinctions (`research/qmd/src/store.ts:758`, `research/qmd/src/store.ts:805`, `research/qmd/src/store.ts:2081` @ `65cd1b3...`). For multimodal indexing, all indexed content is read as UTF-8 text before FTS/vector processing, and the only non-markdown specialization is AST-aware chunking for code text (`research/qmd/src/store.ts:1211`, `research/qmd/src/ast.ts:34`, `research/qmd/src/ast.ts:262` @ `65cd1b3...`).

The recommendation is **reject** for the downstream product's core indexing engine. Monitor QMD only as a small, local, text-first design reference for hybrid markdown retrieval and MCP ergonomics.
