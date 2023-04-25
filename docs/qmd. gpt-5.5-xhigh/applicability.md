# QMD v2.1.0 Applicability Review

## Metadata

- Agent slug: `gpt-5.5-xhigh`
- Subject: `tobi/qmd`
- Pinned tag: `v2.1.0`
- Pinned commit: `65cd1b3fd02891d1ee0eefa751620918664fa321`
- Scope: static review only.

All QMD-specific citations refer to `research/qmd/` at commit `65cd1b3fd02891d1ee0eefa751620918664fa321`.

## Executive Verdict

Recommendation: **Reject** as the downstream product's core indexing substrate.

QMD is a focused local markdown/text search system. It has useful ideas for local hybrid retrieval: content-addressed text storage, SQLite FTS5, `sqlite-vec`, local GGUF embeddings, local query expansion, reciprocal rank fusion, reranking, MCP ergonomics, and AST-aware code chunking (`research/qmd/src/store.ts:746`, `research/qmd/src/store.ts:824`, `research/qmd/src/store.ts:1069`, `research/qmd/src/llm.ts:193`, `research/qmd/src/store.ts:3893`, `research/qmd/src/mcp/server.ts:238`, `research/qmd/src/ast.ts:34` @ `65cd1b3...`).

It does not meet the two repository goals as a primary product foundation. For Sparkle, QMD has collections and context strings but no first-class taxonomy, source connector identity, permissions, ownership, conflict state, or multi-source sync semantics. For multimodal search, QMD reads files as UTF-8 text and has no native image, audio, or video representations (`research/qmd/src/collections.ts:27`, `research/qmd/src/store.ts:1211`, `research/qmd/src/store.ts:1397` @ `65cd1b3...`).

## Goal 1: Sparkle Consistency

Sparkle needs stable preservation of S/P/A/R/K/L/E distinctions across heterogeneous sources. QMD can approximate this only by convention. Collection names, path prefixes, and context strings could encode Sparkle categories, because collections have `name`, `path`, `pattern`, optional `context`, and `includeByDefault` fields (`research/qmd/src/collections.ts:27`, `research/qmd/src/store.ts:875`, `research/qmd/src/store.ts:885` @ `65cd1b3...`). Context is hierarchical by collection/path and can be returned with search results (`research/qmd/src/store.ts:2384`, `research/qmd/src/store.ts:2394`, `research/qmd/src/store.ts:2991` @ `65cd1b3...`).

That is not enough for durable Sparkle consistency. The database schema stores document collection, normalized path, title, hash, timestamps, and active state, but it has no typed Sparkle bucket field, no source account ID, no source object ID, no owner/principal, no permission snapshot, no sync cursor, and no conflict table (`research/qmd/src/store.ts:758`, `research/qmd/src/store.ts:803` @ `65cd1b3...`). Config sync treats external YAML/inline config as authoritative for collection definitions, not as a multi-source reconciliation mechanism (`research/qmd/src/store.ts:1005`, `research/qmd/src/store.ts:1019`, `research/qmd/src/store.ts:1026` @ `65cd1b3...`).

### Sparkle Bucket Mapping

| Sparkle bucket | QMD mapping | Fit |
| --- | --- | --- |
| S - Stream | A collection or inbox folder can be named `stream` and searched by collection/path. | Weak. No lifecycle state for "untriaged" vs processed beyond active/inactive document rows (`research/qmd/src/store.ts:758` @ `65cd1b3...`). |
| P - Projects | Project folders can be separate collections or path prefixes with context. | Medium. Time-bounded project semantics are not modeled; only directory/path conventions exist (`research/qmd/src/collections.ts:27`, `research/qmd/src/store.ts:2384` @ `65cd1b3...`). |
| A - Areas | Areas can be collections or path prefixes. | Medium-low. QMD cannot distinguish non-core Areas from Essentials without external schema (`research/qmd/src/collections.ts:48` @ `65cd1b3...`). |
| R - Resources | Topic folders/collections map reasonably to QMD's text search model. | Medium. Topic reference search is QMD's strongest Sparkle-adjacent use case (`research/qmd/README.md:3`, `research/qmd/README.md:53` @ `65cd1b3...`). |
| K - Knowledge | Could be tagged in context, but QMD cannot represent "internalized expertise." | Weak. Context is descriptive metadata, not evidence of user mastery (`research/qmd/src/collections.ts:31`, `research/qmd/src/store.ts:973` @ `65cd1b3...`). |
| L - Legacy | Archived folders can be indexed as separate collections or excluded by `includeByDefault`. | Medium-low. QMD has `includeByDefault` and active/inactive state, but no archive transition semantics (`research/qmd/src/collections.ts:33`, `research/qmd/src/store.ts:805` @ `65cd1b3...`). |
| E - Essentials | Could be a collection/context, but QMD cannot enforce identity-layer semantics. | Weak. Essentials would collapse into ordinary searchable text (`research/qmd/src/store.ts:746` @ `65cd1b3...`). |

### Source Metadata Preservation

| Requirement | QMD support | Implication |
| --- | --- | --- |
| Source identity | Preserves collection name and normalized relative path; virtual paths are `qmd://collection/path` (`research/qmd/src/store.ts:623`, `research/qmd/src/store.ts:626`, `research/qmd/src/store.ts:758` @ `65cd1b3...`). | Good for one filesystem collection, inadequate for APIs with stable remote IDs. |
| Metadata | Stores title, content hash, created/modified timestamps, active flag, context (`research/qmd/src/store.ts:758`, `research/qmd/src/store.ts:2081` @ `65cd1b3...`). | Minimal metadata only; no arbitrary source metadata bag. |
| Ownership | No owner/user field in schema (`research/qmd/src/store.ts:758` @ `65cd1b3...`). | Must be added externally. |
| Permissions | No ACL/permission snapshot in schema or retrieval filter (`research/qmd/src/store.ts:758`, `research/qmd/src/store.ts:3492` @ `65cd1b3...`). | Cannot preserve source permissions without major changes. |
| Deduplication | Content table is keyed by SHA-256 hash; document rows point to content hashes (`research/qmd/src/store.ts:746`, `research/qmd/src/store.ts:2017`, `research/qmd/src/store.ts:2063` @ `65cd1b3...`). | Good content dedupe primitive, but docids are 6-char hash prefixes and collisions are only partially acknowledged (`research/qmd/src/store.ts:2320` @ `65cd1b3...`). |
| Sync/update semantics | Reindex scans the current filesystem view, updates changed hashes, and marks missing paths inactive (`research/qmd/src/store.ts:1230`, `research/qmd/src/store.ts:1258` @ `65cd1b3...`). | Adequate for local files; insufficient for remote cursors, webhook deltas, conflict resolution, or deletes with provenance. |
| Conflict state | No conflict table or state machine in schema (`research/qmd/src/store.ts:758`, `research/qmd/src/store.ts:803` @ `65cd1b3...`). | Must be built outside QMD. |

Goal 1 verdict: **Low-medium fit**. QMD can be wrapped for simple text notes, but it would distort Sparkle by collapsing taxonomy, source identity, permissions, ownership, and conflict state into naming conventions.

## Goal 2: Multimodal Semantic Indexing

QMD is text-first. Its default glob is `**/*.md`, and the README frames the product around markdown notes, meeting transcripts, documentation, and knowledge bases (`research/qmd/src/store.ts:45`, `research/qmd/README.md:3` @ `65cd1b3...`). Indexing reads each matched file with `readFileSync(filepath, "utf-8")`, hashes the text, extracts a title, and stores the document text (`research/qmd/src/store.ts:1211`, `research/qmd/src/store.ts:1225`, `research/qmd/src/store.ts:1226`, `research/qmd/src/store.ts:1247` @ `65cd1b3...`). Embedding formats text chunks and calls the local embedding model (`research/qmd/src/store.ts:1448`, `research/qmd/src/store.ts:1512`, `research/qmd/src/store.ts:1515` @ `65cd1b3...`).

AST-aware chunking expands the text scope to source code files, not to binary or media modalities. Supported code extensions are TypeScript/TSX/JavaScript/Python/Go/Rust, and unsupported languages fall back to regex text chunking (`research/qmd/src/ast.ts:34`, `research/qmd/src/ast.ts:36`, `research/qmd/src/ast.ts:262`, `research/qmd/src/ast.ts:307` @ `65cd1b3...`).

| Modality | QMD handling | Native multimodal? | Assessment |
| --- | --- | --- | --- |
| Text/markdown | First-class: FTS5, text chunks, text embeddings, text reranking (`research/qmd/src/store.ts:824`, `research/qmd/src/store.ts:1397`, `research/qmd/src/store.ts:3893` @ `65cd1b3...`). | No, text-only embeddings. | Strong for local markdown/text. |
| Source code text | Optional AST-aware chunk boundaries for code files (`research/qmd/src/ast.ts:34`, `research/qmd/src/ast.ts:87`, `research/qmd/src/ast.ts:262` @ `65cd1b3...`). | No, code is still embedded as text. | Useful text/code specialization, not multimodal. |
| Images | No image loader, OCR, CLIP, vision embedding, or image metadata pipeline in indexed path; files are read as UTF-8 text (`research/qmd/src/store.ts:1211` @ `65cd1b3...`). | No. | Unsupported unless preconverted to markdown/text outside QMD. |
| Audio | No ASR/transcription/audio embedding pipeline; meeting transcripts are treated as text if already present (`research/qmd/README.md:3`, `research/qmd/src/store.ts:1211` @ `65cd1b3...`). | No. | Unsupported natively. |
| Video | No video frame, caption, ASR, or video embedding path; binary media would not pass the text pipeline (`research/qmd/src/store.ts:1211` @ `65cd1b3...`). | No. | Unsupported natively. |

Goal 2 verdict: **Low fit**. QMD can consume OCR/ASR/caption outputs if they are materialized as markdown/text, but that is a text-conversion fallback, not native multimodal indexing.

## Embedding And Model Strategy

QMD's model stack is local GGUF via `node-llama-cpp`. Defaults are embeddinggemma for embeddings, Qwen3 reranker, and a fine-tuned QMD query-expansion model (`research/qmd/src/llm.ts:193`, `research/qmd/src/llm.ts:196`, `research/qmd/src/llm.ts:197`, `research/qmd/src/llm.ts:199` @ `65cd1b3...`). Queries/documents are formatted differently for embeddinggemma-style and Qwen3-Embedding-style models (`research/qmd/src/llm.ts:25`, `research/qmd/src/llm.ts:38`, `research/qmd/src/llm.ts:51` @ `65cd1b3...`). Model selection is pluggable through YAML config, environment variables, or `LlamaCppConfig` (`research/qmd/src/collections.ts:37`, `research/qmd/src/llm.ts:354`, `research/qmd/src/llm.ts:438` @ `65cd1b3...`).

This is good for local text retrieval experimentation. It is not enough for the downstream multimodal goal because the model interface exposes text embedding/generation/reranking only (`research/qmd/src/llm.ts:316`, `research/qmd/src/llm.ts:320`, `research/qmd/src/llm.ts:325`, `research/qmd/src/llm.ts:342` @ `65cd1b3...`).

## Source Connectors

Relevant connectors already present:

- Local filesystem collections with glob patterns (`research/qmd/src/collections.ts:27`, `research/qmd/src/store.ts:1189` @ `65cd1b3...`).
- Optional shell `update` commands that can run external sync tools before reindexing (`research/qmd/src/collections.ts:32`, `research/qmd/src/cli/qmd.ts:554` @ `65cd1b3...`).
- SDK inline/config file collection definitions for embedding QMD into Node/Bun applications (`research/qmd/src/index.ts:338`, `research/qmd/src/index.ts:355`, `research/qmd/src/index.ts:360` @ `65cd1b3...`).

Missing connector categories for our needs: Google Drive/Docs, Slack, email, calendar, GitHub APIs, databases, object stores, browser/bookmark sources, photo libraries, audio/video libraries, and any connector that preserves remote permissions and sync cursors. There is no connector registry or source plugin interface in the pinned code; `update()` simply iterates configured collections and calls `reindexCollection` (`research/qmd/src/index.ts:481`, `research/qmd/src/index.ts:492`, `research/qmd/src/store.ts:1180` @ `65cd1b3...`).

## License

QMD is MIT licensed. The package metadata says `"license": "MIT"`, and the license grants use, copy, modification, merge, publication, distribution, sublicense, and sale rights subject to copyright/license inclusion (`research/qmd/package.json:109`, `research/qmd/package.json:110`, `research/qmd/LICENSE:1`, `research/qmd/LICENSE:5` @ `65cd1b3...`). License compatibility is positive for downstream use, subject to normal dependency/license review.

## Maintainer Activity, Governance, And Bus Factor

The changelog shows active development from v1.0.0 through v2.1.0 between 2026-02-15 and 2026-04-05 (`research/qmd/CHANGELOG.md:5`, `research/qmd/CHANGELOG.md:115`, `research/qmd/CHANGELOG.md:247` @ `65cd1b3...`). The v2.1.0 entry says 25+ community PRs fixed embedding stability, BM25 accuracy, and cross-platform launcher issues (`research/qmd/CHANGELOG.md:7`, `research/qmd/CHANGELOG.md:10` @ `65cd1b3...`). Local git metadata at the pinned checkout shows the tag and commit were made by Tobi Lutke, while the changelog credits multiple external contributors in the v2.1.0 release (`research/qmd/CHANGELOG.md:25`, `research/qmd/CHANGELOG.md:30`, `research/qmd/CHANGELOG.md:35`, `research/qmd/CHANGELOG.md:39`, `research/qmd/CHANGELOG.md:41` @ `65cd1b3...`).

Governance is still lightweight. The pinned tree exposes package/release automation and agent skills, but no formal governance document or security policy file was present in static inspection. Bus factor is therefore mixed: active owner plus visible community PRs, but no durable governance process evident in the pinned source.

## Adoption Path And Effort

Possible adoption modes:

| Mode | Effort | Result |
| --- | --- | --- |
| Direct adoption | Low initial, high hidden risk | Not acceptable. It would index only local text/code and lose Sparkle/source/permission/multimodal requirements (`research/qmd/src/store.ts:1211`, `research/qmd/src/store.ts:758` @ `65cd1b3...`). |
| Wrapper around QMD | Medium-high | Could support local markdown collections as one source, but wrapper must own Sparkle schema, source metadata, permissions, sync, and multimodal conversions. QMD would remain a text sub-index. |
| Fork QMD | High | Add typed connectors, permission-aware schema, encrypted storage, non-text pipelines, auth, model provenance, and migration strategy. This is large enough to question why QMD is the base. |
| Upstream contribution | High/uncertain | QMD's project focus is local markdown search; upstreaming heterogeneous/multimodal enterprise concerns may not align with the product's scope (`research/qmd/README.md:3`, `research/qmd/package.json:4` @ `65cd1b3...`). |

Minimum adaptation work for downstream product use:

- Add a schema for source system, source object ID, source revision, owner, permissions, Sparkle bucket, conflict state, sync cursor, deleted/archived state, and metadata bag.
- Replace shell `update` hooks with typed source connectors and per-source sync state (`research/qmd/src/cli/qmd.ts:554` @ `65cd1b3...`).
- Add native modality pipelines for image, audio, and video instead of forcing UTF-8 text reads (`research/qmd/src/store.ts:1211` @ `65cd1b3...`).
- Add modality-specific embedding stores and retrieval fan-out.
- Add authentication/authorization around MCP/HTTP and permission filtering before retrieval (`research/qmd/src/mcp/server.ts:637` @ `65cd1b3...`).
- Add encrypted persistence or use a product-owned secure store (`research/qmd/src/store.ts:746` @ `65cd1b3...`).
- Pin model revisions and record model provenance in index metadata (`research/qmd/src/llm.ts:239` @ `65cd1b3...`).

Honest estimate: a wrapper that only uses QMD for local markdown/code search is **medium** effort. Making QMD the general product substrate is **high to very high** effort and would likely become a fork/rewrite.

## Exit Cost

Exit cost is low if QMD is used only as an optional local markdown index because its source data remains filesystem text and the SQLite schema is simple. Exit cost becomes high if product semantics are embedded in QMD paths/context strings, because Sparkle categories, source identity, and permissions would need to be reconstructed from conventions rather than typed fields (`research/qmd/src/store.ts:758`, `research/qmd/src/store.ts:2384` @ `65cd1b3...`).

## Applicability Checklist

| Question | Answer |
| --- | --- |
| How does the data model map onto Sparkle? | By convention only: collections/path/context can encode buckets, but no native S/P/A/R/K/L/E field or enforcement exists (`research/qmd/src/collections.ts:27`, `research/qmd/src/store.ts:758` @ `65cd1b3...`). |
| Which Sparkle buckets bend/collapse? | K and E collapse into ordinary text; S/L lack lifecycle semantics; P/A/R can be approximated by folders/collections but are not typed (`research/qmd/src/store.ts:746`, `research/qmd/src/collections.ts:33` @ `65cd1b3...`). |
| How are non-text modalities handled? | They are not handled natively. Indexed files are read as UTF-8 text; non-text must be preconverted outside QMD (`research/qmd/src/store.ts:1211` @ `65cd1b3...`). |
| Which metadata survives indexing? | Collection, normalized path, title, hash, timestamps, active state, context, and vector chunk positions survive (`research/qmd/src/store.ts:758`, `research/qmd/src/store.ts:792`, `research/qmd/src/store.ts:2081` @ `65cd1b3...`). |
| Which permissions/ownership/dedup/sync/conflict state survives? | Dedup survives as content hash; sync is scan/update/inactive marking; ownership, permissions, and conflicts do not exist in schema (`research/qmd/src/store.ts:746`, `research/qmd/src/store.ts:1258`, `research/qmd/src/store.ts:758` @ `65cd1b3...`). |
| Which modalities use native multimodal representations? | None. Text/code use text embeddings; image/audio/video have no native representation (`research/qmd/src/llm.ts:316`, `research/qmd/src/ast.ts:34`, `research/qmd/src/store.ts:1211` @ `65cd1b3...`). |
| What embedding/model strategy is used, and is it pluggable? | Local GGUF through `node-llama-cpp`; default embeddinggemma/Qwen reranker/QMD expansion model; pluggable via config/env/SDK (`research/qmd/src/llm.ts:193`, `research/qmd/src/llm.ts:438`, `research/qmd/src/collections.ts:37` @ `65cd1b3...`). |
| Which relevant source connectors already exist? | Local filesystem glob collections and shell update hooks only (`research/qmd/src/store.ts:1189`, `research/qmd/src/collections.ts:32` @ `65cd1b3...`). |
| License compatibility? | MIT, compatible with downstream use subject to notice obligations and dependency review (`research/qmd/LICENSE:1`, `research/qmd/LICENSE:5`, `research/qmd/package.json:110` @ `65cd1b3...`). |
| Maintainer activity/governance/bus factor? | Active release cadence and many credited community PRs; formal governance/security process not evident in pinned tree (`research/qmd/CHANGELOG.md:5`, `research/qmd/CHANGELOG.md:10` @ `65cd1b3...`). |
| Concrete adaptation effort? | High for product core; medium only if limited to a local markdown/code sub-index. |
| Final recommendation? | **Reject** as core substrate; monitor only as a local text-search reference. |
