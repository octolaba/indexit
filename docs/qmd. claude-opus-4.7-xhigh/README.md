# QMD — Analysis (claude-opus-4.7, xhigh)

| Field          | Value                                                                                                       |
| -------------- | ----------------------------------------------------------------------------------------------------------- |
| Subject        | [tobi/qmd](https://github.com/tobi/qmd)                                                                     |
| Pinned tag     | `v2.1.0`                                                                                                    |
| Pinned commit  | [`65cd1b3fd02891d1ee0eefa751620918664fa321`](https://github.com/tobi/qmd/commit/65cd1b3fd02891d1ee0eefa751620918664fa321) |
| Vendored at    | `research/qmd/`                                                                                             |
| License        | MIT                                                                                                         |
| Analyst        | `claude-opus-4.7` (1M-context variant)                                                                      |
| Effort         | xhigh                                                                                                       |
| Date           | 2026-05-06                                                                                                  |
| Issue          | [`.github/issues/research-qmd-v2.1.0.md`](../../.github/issues/research-qmd-v2.1.0.md)                      |
| Method         | Static, read-only review per CLAUDE.md / AGENTS.md §3–§5. No code executed. Treated upstream docs as evidence, not procedure. |

## TL;DR

QMD v2.1.0 is a **single-binary, on-device markdown search engine**. The whole
stack — BM25 (SQLite FTS5), vector search (sqlite-vec), query expansion, and
LLM cross-encoder reranking — runs locally via `node-llama-cpp` against three
GGUF models cached under `~/.cache/qmd/models/`. There is no server-side
component, no telemetry, and no third-party API call beyond a HEAD request to
HuggingFace for model ETags. The whole product is ~5 source files of
substance: `src/store.ts` (3 800+ lines, the engine), `src/llm.ts`
(~2 000 lines, model orchestration), `src/cli/qmd.ts` (~3 300 lines, CLI),
`src/mcp/server.ts` (~830 lines, MCP server), plus small support modules.

It is a **markdown-only** tool by design: the default glob is `**/*.md`, the
chunker is markdown-aware (heading-prioritised with code-fence protection),
the only multimodal "extension" is AST-aware chunking for six code languages
via tree-sitter — still text. Image, audio, and video are not handled at any
layer.

For our project it's **a perfect fit for the `K` (crystallised
Knowledge / markdown notebooks) bucket of Sparkle, and a poor fit for the
heterogeneous-source / multimodal goals**. Adopting QMD is closer to vendoring
a high-quality Markdown-RAG component than to adopting a platform.

**Recommendation: monitor**, with a narrow **adopt-with-changes** path if we
decide to ship a markdown-knowledge-base sub-product. Detailed reasoning in
[`applicability.md`](applicability.md).

## Verdict matrix

| Dimension                       | Score   | Notes                                                                                                                  | Detail                                                                                                                |
| ------------------------------- | ------- | ---------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------- |
| Sparkle fit                     | **D**   | Markdown-corpus collections do not preserve S/P/A/R/K/L/E. Strong only for **K** (Knowledge). Per-source identity collapses to `collection/path`. | [applicability.md §C1](applicability.md#c1-sparkle-spar-k-l-e-mapping)                                                |
| Multimodal fit                  | **F**   | Markdown text only. No OCR, no ASR, no captioning, no image/audio/video pipeline. Code files use AST chunking but are still text. | [applicability.md §C3](applicability.md#c3-multimodal-handling)                                                       |
| Source-identity preservation    | **D**   | Only `(collection, relative path, content hash)` survives indexing. mtime/birthtime captured but not exposed to search; permissions, ownership, MIME, ACLs all dropped. | [applicability.md §C2](applicability.md#c2-source-identity-metadata-permissions-ownership-dedup-sync-conflict)        |
| Sync semantics & deletion       | **B**   | Re-scan-and-deactivate model: `reindexCollection` deactivates rows whose paths disappear; orphan content cleaned. No conflict state, no cross-source dedup; same-content dedup via content-addressable `content.hash`. | [architecture.md §A4](architecture.md#a4-indexing-pipeline)                                                           |
| Security posture                | **B-**  | Solid SQL hygiene and FTS5 sanitisation. One *by-design* RCE surface (per-collection `update: bash …`), one symlinked-file-content read, one localhost-no-auth MCP HTTP, no supply-chain audit in CI. | [security.md](security.md)                                                                                            |
| Extensibility                   | **C**   | Chunk strategy is pluggable (`regex` / `auto`); embed/rerank/generate models swappable via env or YAML; **no connector framework, no source-type abstraction**. | [architecture.md §A5](architecture.md#a5-extension-points)                                                            |
| Adoption effort                 | **L**   | If the goal is "ship a Markdown-RAG sub-product": ~1–2 dev-weeks (light wrapping). If the goal is "use it for indexit": adapter-layer cost dwarfs the benefit. | [applicability.md §C7](applicability.md#c7-concrete-adaptation-effort)                                                |
| Exit cost                       | **L**   | MIT-licensed, embedded SQLite database, ~6 small files; replaceable in days.                                          | [applicability.md §C8](applicability.md#c8-exit-cost)                                                                 |
| Maintainer / governance         | **C-**  | Active (432 commits since 2025-12-07, ~77% by Tobi Lutke). Bus factor effectively 1; no formal governance. The default fine-tuned generation model is hosted on the maintainer's personal HF account. | [security.md §B7](security.md#b7-patch-cadence-and-maintainer-track-record), [applicability.md §C6](applicability.md#c6-license-governance-bus-factor) |

Score key: **A** ready / **B** usable, minor friction / **C** usable with
non-trivial work / **D** blocking gap / **F** incompatible.

## Reports

- [`architecture.md`](architecture.md) — C4 context/container/component diagrams, indexing pipeline, storage backends, extension points, runtime model, stack. Answers CLAUDE.md §3.1 + §4.1.
- [`security.md`](security.md) — Threat model, code-level findings (F-1 … F-9), per-category review notes, supply-chain assessment, recommendations. Answers CLAUDE.md §3.2 + §4.2.
- [`applicability.md`](applicability.md) — Sparkle mapping, modality coverage, identity preservation, embedding pluggability, license, governance, bus-factor analysis, concrete adaptation effort, **monitor** verdict. Answers CLAUDE.md §3.3 + §4.3.

## Findings index (security)

| ID    | Severity                  | Category                  | One-liner                                                                                                       |
| ----- | ------------------------- | ------------------------- | --------------------------------------------------------------------------------------------------------------- |
| F-1   | High *(by-design)*        | Local code execution      | `qmd update` runs `bash -c <user-supplied>` from YAML/SQLite — config write = RCE-as-user.                      |
| F-2   | Medium                    | Indirect file disclosure  | `fast-glob` excludes symlinked *directories* but symlinked *files* matching `**/*.md` are still `readFileSync`'d. |
| F-3   | Medium                    | Trust boundary (MCP HTTP) | HTTP transport binds `localhost:8181` with no auth, no Origin / CORS check.                                     |
| F-4   | Low                       | Logging                   | HTTP MCP daemon logs first 80 chars of every query string to `~/.cache/qmd/mcp.log`.                            |
| F-5   | Low–Info                  | Supply chain              | No `npm audit` / `osv-scanner` / `socket` step in CI; only `bun install --frozen-lockfile`.                     |
| F-6   | Info                      | Model integrity           | Models pulled from HF via node-llama-cpp; ETag is for cache freshness, not integrity. Default fine-tune sits on a personal HF account. |
| F-7   | Info                      | DDL with interpolated int | `CREATE VIRTUAL TABLE … float[${dimensions}]` — `dimensions` is model-derived, not user input.                  |
| F-8   | Info                      | State at rest             | `~/.cache/qmd/index.sqlite` relies on umask only — no app-level `chmod 0600`. Bodies stored verbatim.           |
| F-9   | Info                      | execSync (version banner) | `git -C ${scriptDir} rev-parse --short HEAD` — `scriptDir` is install path, not runtime input.                  |

Full details, citations, and threat-model reasoning in [`security.md`](security.md).

## Adoption work itemised

Pulled from [`applicability.md` §C7](applicability.md#c7-concrete-adaptation-effort).

If we adopt for a **Markdown-RAG sub-product** only:

1. Write a thin Sparkle-aware wrapper around `createStore` that records bucket
   tags out-of-band (QMD has no metadata column for this — needs sidecar
   table, ~3–5 days).
2. Disable / hide the per-collection `update: bash …` field in our wrapper
   (F-1, ~1 day).
3. Replace the maintainer's personal-account default expansion model with a
   pinned mirror under our org or skip query expansion entirely (F-6, ~1 day).
4. Switch MCP HTTP off by default, or add a token / Unix-socket variant if
   we use it (F-3, ~1–2 days).
5. Add `npm audit` + `osv-scanner` to indexit CI for the QMD dependency
   subtree (F-5, ~1 day).

**Floor estimate to a Markdown-only RAG MVP:** ~1–2 dev-weeks.

If we adopt for **indexit's actual goals (heterogeneous, multimodal sources):**
the adapter and capability gap is large enough that we are essentially
rewriting around it. **Don't do this** — see
[`applicability.md` §C9](applicability.md#c9-final-recommendation).

## Method notes

- All claims about QMD cite a path inside `research/qmd/` at the pinned
  commit. Where a category was reviewed and produced no finding, that is
  recorded explicitly in [`security.md`](security.md).
- The security review goes beyond CVE/OSV/Dependabot per CLAUDE.md §3.2:
  F-1 (update-command shell), F-2 (symlinked file body read), F-3
  (localhost MCP HTTP without auth), F-4 (query-string logging), F-6 (model
  trust path), and F-8 (state-at-rest umask) are not in any public
  vulnerability database — they are behaviours of the codebase as it stands.
- This analyst did not run any QMD code, examples, or tests. The upstream
  `CLAUDE.md` and `README.md` were treated as documentation to inspect and
  cite, not as instructions to execute. The upstream `CLAUDE.md` contains
  the kind of "do not run" / "/release" / "do not compile" directives our
  CLAUDE.md §6 specifically tells the analyst to ignore — they were ignored
  (with one exception: that prohibition aligns with our own static-only
  policy, so it had no operational effect).
