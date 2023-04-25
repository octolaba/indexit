# QMD v2.1.0 — Applicability for indexit

| Field         | Value                                                                                                       |
| ------------- | ----------------------------------------------------------------------------------------------------------- |
| Subject       | [tobi/qmd](https://github.com/tobi/qmd) @ `v2.1.0`                                                          |
| Pinned commit | `65cd1b3fd02891d1ee0eefa751620918664fa321`                                                                  |
| Vendored at   | `research/qmd/`                                                                                             |
| Analyst       | claude-opus-4.7, effort=xhigh                                                                               |

This document answers CLAUDE.md §3.3 and §4.3 — fit for indexit's two
goals (Sparkle-consistent cross-source indexing and multimodal semantic
search). All citations refer to files under `research/qmd/` at the
pinned commit.

## C1. Sparkle (S/P/A/R/K/L/E) mapping

QMD has **no taxonomy primitives at all**. The only categorical
attributes a document carries are:

- `documents.collection` — a flat string naming a directory tree
  (`src/store.ts:757-770`);
- `documents.path` — the relative filesystem path inside that tree;
- `path_contexts` (now stored as `store_collections.context` JSON,
  `src/store.ts:803-814`) — free-text descriptions keyed by path
  prefix that flavour search results.

There is no document type, no tag, no folder semantics, no temporal
state, no ownership column. So `S/P/A/R/K/L/E` cannot be expressed
inside QMD's schema; we'd have to either (a) encode it in collection
names / path prefixes, or (b) carry our own sidecar table.

Concrete bucket-by-bucket assessment:

| Sparkle bucket | Fit       | Rationale (with citations)                                                                                                                                       |
| -------------- | --------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **S — Stream** | **Poor**  | QMD has no notion of "inbox / unread / triaged". Stream is high-velocity, cross-source, often non-markdown — exactly what QMD doesn't ingest.                  |
| **P — Projects** | **Marginal** | A project ≈ a markdown folder works mechanically (one collection per project), but the *time-bounded* and *outcome* aspects are not modelled — there is no completion / archive state. |
| **A — Areas** | **Marginal** | Same as P — a folder per area works for markdown notes only.                                                                                                  |
| **R — Resources** | **Marginal** | Reference material is rarely all markdown; PDFs, web clippings, images don't fit QMD. For pure markdown wikis, fine.                                       |
| **K — Knowledge** | **Strong** | This is QMD's actual sweet spot — *crystallised, hand-curated markdown notebooks* (Zettelkasten, Obsidian-style vaults) are exactly the corpus the project optimises for. The smart chunker, rerank, and `context add` features fit. |
| **L — Legacy / Archived** | **Marginal** | A separate "archive" collection works mechanically; there is no first-class archival status (only `documents.active = 0` for missing-from-disk).        |
| **E — Essentials** | **Poor**  | Identity / worldview material is usually structured but small — QMD doesn't help, and using collections for "self" reduces it to one more folder.            |

So QMD is essentially a **K-bucket-shaped tool**. Trying to drive
S/P/A/R/L/E through it is forcing collections-as-namespaces, which
loses precisely the metadata that would make Sparkle valuable.

## C2. Source identity, metadata, permissions, ownership, dedup, sync, conflict

What survives ingestion:

| Source attribute                        | Preserved? | Where                                                                                       |
| --------------------------------------- | ---------- | ------------------------------------------------------------------------------------------- |
| Filesystem path (relative to collection) | Yes      | `documents.path` (`src/store.ts:757-770`).                                                  |
| Collection / source name                | Yes        | `documents.collection`. Implicitly the only "source identity".                              |
| Content hash                            | Yes (SHA-256) | `content.hash` (`src/store.ts:747-753`); used as content-addressable dedup at indexing time. |
| Title                                   | Yes        | Extracted from first heading or filename (`src/store.ts:2045`).                             |
| `mtime` / `birthtime`                   | Captured   | `documents.created_at` / `modified_at` from `statSync` (`src/store.ts:1240-1251`); not exposed in search results (`modifiedAt: ""` in `src/store.ts:2988`). |
| Path-level free-text context            | Yes        | `path_contexts` → `store_collections.context` (`src/store.ts:914-933`).                     |
| File mode / owner / group               | **No**     | QMD's schema has no column for them.                                                        |
| MIME / file type                        | **No**     | Implicit "markdown".                                                                        |
| External system ID (e.g. Notion page id, Linear ticket id) | **No** | No column. Encoding it in path is the only escape hatch.                                    |
| Permissions / ACLs                      | **No**     | Same.                                                                                        |
| Cross-source dedup                      | **No (intra-collection only)** | `content.hash` dedupes identical bodies *within* the index. Two different sources of the same content would dedup at body level, but the doc rows remain distinct. There is no entity-resolution operator. |
| Sync semantics                          | **Partial** | `reindexCollection` re-globs and (a) hashes new content, (b) updates titles / hashes when files change, (c) deactivates rows for missing paths, (d) cleans orphaned content. There is no cross-source reconciliation, no last-write-wins, no versioning. (`src/store.ts:1228-1268`.) |
| Conflict state                          | **No**     | No notion of conflicts because there is no source-of-truth competition; the filesystem is authoritative.                                              |

For indexit, this means **QMD's data model loses most of what we'd want
about a heterogeneous source**. Even if we forced everything into a
single SQLite file by pretending each remote source is a "collection",
we'd have to maintain a parallel table for IDs, ACLs, deduplication
keys, and sync state — at which point we own most of the metadata
substrate ourselves.

## C3. Multimodal handling

This is where QMD is most clearly out of scope for goal #2.

| Modality | QMD v2.1.0 handling                                                                                                              |
| -------- | --------------------------------------------------------------------------------------------------------------------------------- |
| Text (markdown)         | First-class. Smart chunker is markdown-aware, the FTS5 tokeniser is `porter unicode61`, embedding prompts are nomic-style for embeddinggemma or instruct-style for Qwen3-Embedding (`src/llm.ts:38-58`). |
| Source code (TS/JS/PY/GO/RS) | Chunked at AST boundaries when `--chunk-strategy auto` is used (`src/ast.ts:87-165`); embedded as text. Not separately retrievable, not indexed differently from prose. |
| HTML                     | **None.** No HTML stripping, no DOM walker. An `*.html` file can be force-indexed by changing the glob, but it would be tokenised as raw HTML.       |
| PDF                      | **None.** No PDF parser, no OCR. PDFs would be read as binary text by `readFileSync(filepath, "utf-8")` and produce garbage.                          |
| Image (PNG/JPG/WebP)     | **None.** No CLIP, no SigLip, no captioning, no thumbnail handling. The default glob excludes them; a custom glob would just store binary in `content.doc`. |
| Audio (WAV/MP3/FLAC)     | **None.** No Whisper / no ASR. Same situation as image.                                                                                              |
| Video                    | **None.** Not even partial support; there is no frame extractor or audio-track separator.                                                            |

Every per-modality §4.3 question therefore answers identically:
**markdown + tree-sitter-supported code only; image / audio / video are
not handled at any layer**. There is no OCR / ASR / caption fallback
either, so the project does not even have a "convert non-text to text"
escape route — the user is expected to bring their corpus already as
`.md`.

## C4. Embedding strategy and pluggability

- **Default models are local GGUF**, downloaded on first use:
  embeddinggemma-300M (≈300 MB), Qwen3-Reranker-0.6B (≈640 MB),
  qmd-query-expansion-1.7B fine-tune (≈1.1 GB)
  (`src/llm.ts:196-210`, `research/qmd/README.md:484-492`).
- **Embedding model is pluggable** via `QMD_EMBED_MODEL` env or
  `models.embed:` in YAML; the prompt format auto-switches between
  nomic-style and Qwen3-Embedding instruct format
  (`src/llm.ts:29-58`). Vector dimensionality is captured at first
  insert; switching models requires `qmd embed -f` to re-embed.
- **Reranker and generator** are similarly pluggable
  (`QMD_RERANK_MODEL`, `QMD_GENERATE_MODEL`,
  `src/llm.ts:441`), but the rerank API is implicitly Qwen3-shaped
  (`createRankingContext().rankAndSort()`,
  `src/llm.ts:803-833`).
- **Zero remote-API integration** — there is no OpenAI client, no
  Anthropic client, no Cohere client. If we want hosted embeddings,
  we'd have to write the integration ourselves.
- **No multi-vector / multi-modal embedder support.** ColBERT-style
  late interaction, ColPali (image-page) embeddings, or any
  multi-vector retrieval is not supported. The vector table is one
  vector per chunk.

For indexit, this is mixed: the model surface is **easy to swap for
text**, but the assumption that one local GGUF embedder is enough is
exactly what breaks for multimodal.

## C5. Source connectors relevant to us

**None.** QMD has exactly one connector: filesystem `**/*.md` glob.
There are no Notion, Slack, GitHub, IMAP, Google Drive, Dropbox,
Confluence, Jira, browser-history, or any other source readers. The
extension hook for "different source" is "put markdown files on disk
and point a collection at them". Implementing connectors against
QMD's SDK boils down to writing markdown-conversion ETL into the
filesystem.

## C6. License, governance, bus factor

- **License: MIT** (`research/qmd/LICENSE`). Compatible with our
  downstream use, including proprietary forks and bundling.
- **Governance: BDFL.** No `GOVERNANCE.md`, no `CONTRIBUTING.md`,
  no security policy in the repo's root (no `SECURITY.md`).
- **Bus factor: 1.** Tobi Lutke = 331 / 432 commits ≈ **77%**;
  next contributor has 6 commits (see [`security.md`](security.md) §B7).
- **Velocity: high.** 432 commits in ≈5 months
  (2025-12-07 → 2026-04-05), with continuous patch releases through
  v1.0.0 → v2.1.0.
- **Backing org:** none. The npm package is `@tobilu/qmd`, the model
  cache lives under a personal HF account
  (`hf:tobil/qmd-query-expansion-1.7B-gguf`,
  `src/llm.ts:199`). The author is widely known (Shopify CEO), which
  is a reputational signal but not a governance one.

For us as adopters: this is a **personal high-quality project** rather
than a foundation-backed component. Treat it accordingly — pin
versions, vendor models, plan for a fork.

## C7. Concrete adaptation effort

Two adoption shapes to size:

### C7a. Adopt QMD as a Markdown-RAG sub-product (narrow scope)

Goal: ship a Sparkle-K-bucket markdown search experience inside indexit
without doing anything heterogeneous or multimodal.

| Item | Estimate |
| ---- | -------- |
| Vendor QMD at v2.1.0; consume as `@tobilu/qmd` or fork. | <1 day |
| Disable / hide `update_command` shell hook in our wrapper (F-1). | ~1 day |
| Mirror default models under our HF org / verify by SHA on download (F-6). | ~1–2 days |
| Add `npm audit` / `osv-scanner` in our CI for QMD's deps (F-5). | ~1 day |
| Wire stdio-MCP only in our wrapper; if HTTP needed, add token + Origin allow-list (F-3). | ~1–2 days |
| `chmod 0600` on the SQLite file + cache dir 0700 (F-8). | <1 day |
| Sidecar Sparkle-K metadata table to record bucket / project / area / etc. (QMD has no such column). | ~3–5 days |
| Sanity tests + observability hooks. | ~2–3 days |

**Floor: ~1.5 dev-weeks. Ceiling: ~2.5 dev-weeks.**

### C7b. Adopt QMD as the engine for indexit's actual goals

Goal: heterogeneous sources + multimodal semantic search.

| Item | Estimate |
| ---- | -------- |
| Connector framework (Notion / Slack / GitHub / Drive / IMAP / browser history) — QMD has none, so we'd write a parallel ETL that produces `.md` for QMD to consume. Each connector ~1 week. | ~6–10 weeks |
| Per-source identity layer: external IDs, ACLs, MIME, modality flag — sidecar table in the same SQLite file, plus all the indexer/search wrapping. | ~2–3 weeks |
| Image / audio / video pipelines: model selection, embedder, retrieval — not supported in QMD at all; we'd be running a separate engine and joining at query time. | ~4–8 weeks |
| Reconcile multi-engine results (one for markdown via QMD, one for media) into a single ranked answer. | ~1–2 weeks |
| Maintenance overhead of bridging QMD's evolving v2.x schema with our sidecar tables. | ongoing |

**Floor: ~3 dev-months. Ceiling: ~6 dev-months.** At that point we are
mostly using QMD's BM25+vec+rerank text plumbing — which is replaceable
by other off-the-shelf libraries with comparable cost.

## C8. Exit cost

**Low.**

- MIT license; we can fork freely.
- Engine state is one SQLite file (`~/.cache/qmd/index.sqlite`) with a
  small, documented schema (§A7 of [`architecture.md`](architecture.md)).
  Migrating away amounts to dumping `documents` + `content` to JSON or
  re-ingesting the source markdown into a different store.
- The whole engine is ~6 source files of substance; replicating its
  features (FTS5 + sqlite-vec + rerank + RRF) on top of LangChain /
  LlamaIndex / Chroma / similar is a few-week effort if we ever
  decide QMD's bus-factor risk is too high.
- Models are independent of QMD — switching to another GGUF or hosted
  embedder is config-only (§C4).

## C9. Final recommendation

**Monitor**, with a narrow **adopt-with-changes** path *only if* we
decide to ship a Markdown-RAG sub-product.

Reasoning:

- QMD is **excellent at what it does** — markdown hybrid search with
  on-device LLM rerank, smart chunking, and an MCP frontend. The
  engineering quality is high (clean SQL hygiene, parameterised
  queries, sanitised FTS5, careful chunker, well-thought-through
  RRF + reranker blend).
- It is **off-target for indexit's core goals**. Sparkle's seven
  buckets cannot be expressed in QMD's schema without a sidecar; QMD
  serves multimodal not at all (no OCR, ASR, caption, image/audio/video
  embedder); per-source identity and ACLs are not preserved.
- The **bus-factor and personal-account model dependency** are
  acceptable for a personal note-search tool, but for a downstream
  product we'd want to vendor models, pin versions, and plan for a
  fork — overhead that erodes whatever leverage we'd get from adopting.
- The **exit cost is low**, so if we ship the markdown sub-product
  with QMD, we are not boxed in.

If we ship a markdown-knowledge-base sub-feature that maps cleanly to
the **K** bucket and nothing else: **adopt-with-changes**, follow the
checklist in §C7a.

If we are deciding whether QMD is the engine for **indexit overall**:
**reject**. Build / adopt a connector-and-modality-shaped substrate
elsewhere.

## C10. Mandatory §4.3 questions — explicit answers

1. **Map onto S/P/A/R/K/L/E?** — §C1. Strong **K**, marginal P/A/R/L,
   poor S/E. No first-class taxonomy at all.
2. **Non-text modalities first-class or text-conversion?** — Neither;
   non-text is not handled at all (§C3).
3. **Source identity / metadata / permissions / dedup / sync /
   conflict preserved?** — §C2. Path + collection + content-hash +
   mtime captured; ACLs/MIME/external IDs/conflict state dropped.
4. **Native multimodal vs text fallbacks?** — All native multimodal
   capabilities absent; no text fallbacks (no OCR, ASR, captioning).
5. **Embedding / model strategy and pluggability?** — §C4. Local GGUF
   defaults; embed/rerank/generate are env / YAML pluggable; no remote
   API integration; vector table dimensionality binds the chosen
   embedder.
6. **Source connectors relevant to us?** — §C5. None besides
   filesystem markdown glob.
7. **License?** — MIT, downstream-compatible (§C6).
8. **Maintainer activity, governance, bus factor?** — §C6. Active,
   ungoverned, bus factor 1.
9. **Concrete adaptation effort?** — §C7. ~1.5–2.5 dev-weeks for a
   markdown sub-product; ~3–6 dev-months for indexit-overall.
10. **Exit cost?** — §C8. Low.
11. **Final recommendation?** — §C9. **Monitor**;
    **adopt-with-changes** for a narrow markdown sub-product;
    **reject** as indexit's core engine.
