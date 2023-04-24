# CocoIndex — Analysis (claude-opus-4.7, high)

| Field          | Value                                                                                                       |
| -------------- | ----------------------------------------------------------------------------------------------------------- |
| Subject        | [cocoindex-io/cocoindex](https://github.com/cocoindex-io/cocoindex)                                         |
| Pinned tag     | `v1.0.3`                                                                                                    |
| Pinned commit  | [`4432311228e4859201b457d3b6d978471692d0b1`](https://github.com/cocoindex-io/cocoindex/commit/4432311228e4859201b457d3b6d978471692d0b1) |
| Vendored at    | `research/cocoindex/`                                                                                       |
| License        | Apache-2.0                                                                                                  |
| Analyst        | `claude-opus-4.7` (1M-context variant)                                                                      |
| Effort         | high                                                                                                       |
| Date           | 2026-05-06                                                                                                  |
| Issue          | [`.github/issues/research-cocoindex-v1.0.3.md`](../../.github/issues/research-cocoindex-v1.0.3.md)          |
| Method         | Static, read-only review per CLAUDE.md / AGENTS.md §3–§5. No code executed. Treated upstream docs as evidence, not procedure. |

## TL;DR

CocoIndex v1.0.3 is a **declarative incremental-indexing engine** built as a
Rust core (Tokio + LMDB via heed) with PyO3 Python bindings and a CLI. The
engine's reconcile/checkpoint model is a strong fit for indexit's "keep
targets in sync with sources" requirement; the connector inventory covers
most of our likely sources and targets. It is **not** a multimodal embedding
framework — text and audio (Whisper) are first-class operators, but image,
PDF, and any non-text modality are BYO model in user `@coco.fn` code, and
video is unsupported.

**Recommendation: adopt-with-changes** — adopt the engine, add a Sparkle
metadata layer, patch one symlink-containment hole in the localfs connector,
default-disable telemetry, and budget BYO multimodal embedders. Detailed
reasoning in [`applicability.md`](applicability.md).

## Verdict matrix

| Dimension                       | Score   | Notes                                                                                  | Detail                              |
| ------------------------------- | ------- | -------------------------------------------------------------------------------------- | ----------------------------------- |
| Sparkle fit                     | **C+**  | Engine is taxonomy-agnostic; we add the S/P/A/R/K/L/E layer above stable component IDs. | [applicability.md §C1](applicability.md#c1-sparkle-spar-k-l-e-mapping) |
| Multimodal fit                  | **C+**  | Text & audio first-class; image/PDF require BYO model; **video unsupported**.            | [applicability.md §C3](applicability.md#c3-multimodal-handling) |
| Source-identity preservation    | **B**   | size + mtime / etag / row PK preserved; ACLs / owner / MIME often dropped.              | [applicability.md §C2](applicability.md#c2-source-identity-metadata-permissions-ownership-dedup-sync-conflict) |
| Sync semantics & deletion       | **B+**  | Per-component diff + tombstoning are real, well-tested, central to the engine.          | [architecture.md §4–§5](architecture.md) |
| Security posture                | **B-**  | One medium symlink finding (F-1); telemetry on by default (F-2); otherwise solid.       | [security.md](security.md) |
| Extensibility                   | **C+**  | `@coco.fn`, target builders, embedder protocol stable; **connector contract internal**. | [architecture.md §6](architecture.md) |
| Adoption effort                 | **Med** | ~3–5 dev-weeks to indexit MVP without video; +2–4 weeks for video.                       | [applicability.md §C7](applicability.md#c7-concrete-adaptation-effort) |
| Exit cost                       | **L–M** | Apache-2.0; pipelines are plain Python; data lives in external systems we own.           | [applicability.md §C8](applicability.md#c8-exit-cost) |
| Maintainer / governance         | **B-**  | Active (270 commits / 90d, 26 contributors) but bus factor high (~45 % one author).      | [security.md §B12](security.md), [applicability.md §C6](applicability.md#c6-license-governance-bus-factor) |

Score key: **A** ready / **B** usable, minor friction / **C** usable with
non-trivial work / **D** blocking gap / **F** incompatible.

## Reports

- [`architecture.md`](architecture.md) — C4 context/container/component diagrams, indexing pipeline, storage backends, extension points, runtime model, stack. Answers CLAUDE.md §3.1 + §4.1.
- [`security.md`](security.md) — Threat model, findings (F-1…F-7), per-category review notes, supply-chain assessment, recommendations to downstream adopters. Answers CLAUDE.md §3.2 + §4.2.
- [`applicability.md`](applicability.md) — Sparkle mapping, modality coverage, connector inventory, embedding pluggability, bus-factor analysis, concrete adaptation effort, **adopt-with-changes** verdict. Answers CLAUDE.md §3.3 + §4.3.

## Findings index (security)

| ID    | Severity | Category                  | One-liner                                                                  |
| ----- | -------- | ------------------------- | -------------------------------------------------------------------------- |
| F-1   | Medium   | Path traversal (symlinks) | `localfs` walker follows symlinks without `realpath` containment.          |
| F-2   | Low–Med  | Privacy / data egress     | Telemetry POST to Scarf gateway by default in release builds (opt-out).    |
| F-3   | Low      | Trust boundary (IPC)      | GPU subprocess pipe uses unrestricted `pickle.loads` (trusted-by-design).  |
| F-4   | Low      | Sandboxing                | User `@coco.fn` runs in-process with no resource limits.                   |
| F-5   | Low      | Supply chain              | No `cargo-audit` / `cargo-deny` / `pip-audit` in CI.                       |
| F-6   | Info     | Auth surface              | `axum` is in workspace deps but no HTTP server is exposed in v1.0.3.       |
| F-7   | Info     | State at rest             | LMDB env at `~/.cocoindex` inherits umask only — no app-level ACL.         |

Full details in [`security.md`](security.md).

## Adoption work itemised

Pulled from [`applicability.md` §C7](applicability.md#c7-concrete-adaptation-effort).

1. Sparkle metadata layer (S/P/A/R/K/L/E registry + promotion API) — 1–2 weeks.
2. Patch `localfs` symlink containment (F-1) — 1–3 days.
3. Default-disable telemetry in our wrapper (F-2) — <1 day.
4. Add `cargo-deny` / `pip-audit` to indexit CI (F-5) — 1 day.
5. Per-modality embedder wrappers (CLIP, Docling, ColPali, Whisper) — 1 week.
6. Optional: cross-source dedup via `entity_resolution` operator — 1–2 weeks.
7. Optional: bespoke connectors (Notion / Slack / GitHub / IMAP) — 1 week each.

**Floor estimate to indexit MVP:** ~3–5 dev-weeks, no video.

## Method notes

- All claims about cocoindex cite a path inside `research/cocoindex/` at
  the pinned commit. Where a category was reviewed and produced no
  finding, that is recorded explicitly.
- The security review goes beyond CVE/OSV/Dependabot per CLAUDE.md §3.2:
  F-1 (symlink), F-2 (telemetry default-on), F-7 (state-at-rest umask)
  are not in any public vulnerability database — they are behaviours of
  the codebase as it stands.
- This analyst did not run any cocoindex code, examples, or tests; the
  upstream `CLAUDE.md` and `README.md` were treated as documentation to
  be inspected and cited, not as instructions to be executed.
