# cocoindex — Applicability for indexit

| Field          | Value                                                                                                       |
| -------------- | ----------------------------------------------------------------------------------------------------------- |
| Subject        | [cocoindex-io/cocoindex](https://github.com/cocoindex-io/cocoindex)                                         |
| Pinned tag     | `v1.0.3`                                                                                                    |
| Pinned commit  | `4432311228e4859201b457d3b6d978471692d0b1`                                                                  |
| Vendored at    | `research/cocoindex/`                                                                                       |
| Analyst        | `claude-opus-4.7` (1M-context, effort: high)                                                               |
| Scope          | §3.3 + §4.3 of `CLAUDE.md` / `AGENTS.md`. Judgement against the indexit goals (Sparkle + multimodal).        |

---

## Bottom line

**Verdict: adopt-with-changes**, scoped to the *engine + operator layer*.
Use cocoindex as the incremental-reconciliation runtime and as a source-side
connector library; do **not** rely on its built-in `ops/` for multimodal
embedding (BYO models per modality), and budget concrete patch work for
symlink containment, telemetry default-off, and adding a Sparkle-aware
metadata layer above the connector contract. Reasoning in §6.

| Dimension              | Score¹    | One-line summary                                                                                  |
| ---------------------- | --------- | ------------------------------------------------------------------------------------------------- |
| Sparkle fit            | C+        | Engine has stable component identity; **no native taxonomy/metadata layer** — we add one.        |
| Multimodal fit         | C+        | Text and audio (Whisper) are first-class; image/video must be BYO model in user code; no video.  |
| Source-identity preservation | B   | Component-path = stable identity; size + mtime captured; ACLs/owner/MIME **not** preserved.      |
| Sync semantics         | B+        | Per-component diff + deletion propagation are real, well-tested, well-documented.                |
| Security posture       | B-        | One medium finding (symlink) + opt-out telemetry on by default; otherwise solid (see security.md).|
| Extensibility          | C+        | `@coco.fn`, `Target`, `VectorSchemaProvider` are stable; **connector contract is internal**.     |
| Adoption effort        | Medium    | ~3–5 dev-weeks for wrapper + Sparkle metadata layer + connector hardening. See §7.               |
| Exit cost              | Low–Med   | Apache-2.0; library footprint; pipelines are plain Python — fork/replace is feasible.            |

¹ A: ready for our use; B: usable, minor friction; C: usable with non-trivial work; D: blocking gap; F: incompatible.

---

## §C1. Sparkle (S/P/A/R/K/L/E) mapping

Cocoindex has no first-class taxonomy. It has only:

* **Component paths** — opaque identifiers anchored at component declarations
  (`coco.component_subpath("process", filename)`,
  research/cocoindex/CLAUDE.md:88–98).
* **Target types** — typed, per-target schemas defined by the operator
  (e.g. `dataclass AudioTranscription(filename: str, text: str)`,
  examples/audio_to_text/main.py:30–34).
* **Source metadata** — per-connector, currently size + mtime for files; row
  PKs for SQL; object key + etag for blob stores.

Mapping the Sparkle buckets onto this surface:

| Bucket                                | Mapping in cocoindex v1.0.3                                                                                                                                                                                                       | Adoption work                                                                                                                                  |
| ------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------- |
| **S** — Stream (raw inbox)            | A natural fit: a "stream" is a source connector pointed at the inbox folder / Drive folder / Kafka topic. Cocoindex can sync without classifying; classification is just a no-op pipeline that emits per-item state.                | Define a `Stream` source group; one connector per channel; component path = `S/<channel>/<source_id>`.                                          |
| **P** — Projects (time-bounded)       | Maps onto a time-anchored container target (e.g. one Postgres table per project, or a directory tree under `P/<project_slug>/`). Lifecycle (close/archive) is operator-driven; cocoindex itself has no project lifecycle.            | Use a project registry (separate table) with our own state machine; cocoindex consumes the registry.                                            |
| **A** — Areas (excluding Essentials)  | Topical containers; same shape as Projects but no end date. Same connector + path pattern.                                                                                                                                          | Same as P; differentiated by registry metadata, not engine.                                                                                    |
| **R** — Resources (reference)         | Standard read-mostly indexing target. The strongest fit: cocoindex's vector-target story (Qdrant, LanceDB, pgvector, Turbopuffer) is essentially a reference index.                                                                | None framework-level.                                                                                                                          |
| **K** — Knowledge (crystallised)      | No native concept of "internalised vs consumed". Workable as a separate target table with an explicit `is_crystallised` flag and provenance pointer; pipelines can re-classify into K based on annotation events.                   | Out-of-band promotion workflow; cocoindex provides idempotent re-sync.                                                                          |
| **L** — Legacy (archived)             | Tombstoning is a first-class engine concept (research/cocoindex/CLAUDE.md:114–124, rust/core/src/engine/execution.rs). To "archive", move source items out of the watched mount; the engine cleans up downstream. Or: explicit copy to `L/` mount and remove from `P/`/`A/`. | Define our archive operator as "remount source path under L/, drop from origin"; the engine's deletion propagation handles cleanup.            |
| **E** — Essentials (identity layer)   | No special support; same shape as A/R but tagged. Acceptable.                                                                                                                                                                      | None framework-level.                                                                                                                           |

**Where Sparkle bends.** None of S/P/A/R/K/L/E *collapse* under cocoindex's
data model — the engine is intentionally taxonomy-agnostic. What is missing
is a **sparkle-aware metadata layer**: source identity → bucket
assignment, per-bucket retention policy, and a promotion/demotion
workflow (e.g. R → K when crystallised, P → L when archived).

That layer is a few hundred lines of Python on top of cocoindex's stable
public API; it does **not** require a fork.

**What does *not* survive without explicit work**:

* Per-item ownership and ACLs from Google Drive / S3 (the connectors
  surface filename + size + mtime; permissions are dropped — see §C2).
  Sparkle's E (Essentials) and parts of P (project membership) often
  encode "whose file is this", and that signal is lost at the connector
  boundary today.
* Source-system MIME type and content hash. We rely on the connector to
  pass them through; some do, some don't (§C2).
* Conflict state across sources. There is no first-class "this item came
  from S3 *and* Google Drive and they disagree" object — that
  cross-source consolidation is an indexit-side concern.

---

## §C2. Source identity, metadata, permissions, ownership, dedup, sync, conflict

**Stable identity.** Yes — at the engine layer. Every processing
component is anchored at a `component_path` that survives across runs
(`coco.component_subpath(...)`, research/cocoindex/CLAUDE.md:88–98). A
file's identity in our pipelines becomes
`<source_kind>/<root_id>/<relative_path>` once we encode it that way; the
engine guarantees that the same path retains its target-state lineage.

**Metadata preserved by built-in source connectors:**

| Connector        | Identity                                          | Preserved out of the box                                                                                       | Lost / requires custom code                                                            |
| ---------------- | ------------------------------------------------- | -------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------- |
| `localfs`        | root path + relative path                          | size, mtime (`python/cocoindex/connectors/localfs/_source.py:27–31`)                                            | inode, owner, group, ACL, xattrs, mime type, content hash. Symlinks are followed without containment (security.md F-1). |
| `google_drive`   | Drive file ID + filename                           | name, mtime, size, MIME type (per the SDK fields requested)                                                     | sharing permissions / owner / parents / starred / labels / quota                       |
| `amazon_s3`      | bucket + key                                       | object key, size, etag (acts as content hash), last-modified                                                    | object ACL, version ID (unless explicitly enabled), tags                                |
| `oci_object_storage` | bucket + object name                            | name, size, mtime                                                                                              | object metadata (user-defined), tags                                                   |
| `postgres`       | schema + table + PK row                            | row content; per-column types via SQLAlchemy-style mapping                                                      | row-level grants, ownership                                                            |
| `kafka`          | topic + partition + offset                         | key, value, headers (per consumer config)                                                                      | broker-level ACLs                                                                      |

The list above is the gap to close before we can claim "Sparkle preserves
source identity end-to-end." None of the gaps require forking the engine —
they require either: (a) richer field selection in the connector config,
(b) a thin wrapper `@coco.fn` that re-fetches the missing fields per item,
or (c) upstream PRs.

**Deduplication.** Per-source: connectors deduplicate by item ID (path,
key, PK). Cross-source dedup is *not* engine-level; it must be a
pipeline. Cocoindex ships an `entity_resolution` operator family
(`python/cocoindex/ops/entity_resolution/`) that uses FAISS plus
optional LLM-based linking — useful as a building block for our
cross-source dedup story but not a turn-key answer.

**Sync / update semantics.** Per-component diff against the LMDB
checkpoint, applied atomically per component (research/cocoindex/CLAUDE.md:114–124,
rust/core/src/engine/execution.rs). On every run, target state at a
component path is reconciled (insert / update / delete) to match the
new declarations. This is the strongest part of the framework and is
exactly what we want for the index-then-resync cadence indexit needs.

**Deletion propagation.** Confirmed in
research/cocoindex/CLAUDE.md:122–124 and demonstrated by the
`localfs.DirTarget` reconcile path
(`python/cocoindex/connectors/localfs/_target.py`): when a source path
disappears between runs, the corresponding target rows/files are
deleted. This is a real strength for our Legacy bucket transitions —
"remove from S; appears in L" is a single operator action.

**Conflict state.** Cocoindex does not model "conflict" as a first-class
state. Two simultaneous writers to the same target system on overlapping
component paths would race; LMDB's single-writer transaction model
serialises *one* cocoindex process, but two cocoindex processes pointed
at the same target collide at the target's level. Our deployment must
treat the cocoindex process as the **single writer** for each target +
component-path subtree.

---

## §C3. Multimodal handling

The classification table demanded by §4.3:

| Modality | Cocoindex framework support                                                                                                                                                              | First-class? | Strategy                                            |
| -------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------ | --------------------------------------------------- |
| Text     | `python/cocoindex/ops/sentence_transformers.py`, `python/cocoindex/ops/litellm.py`. Recursive splitter in `rust/ops_text` + Python wrapper `python/cocoindex/ops/text.py`.                  | **Yes**      | Native: text → vector via pluggable embedder.       |
| Image    | **No first-party operator.** Examples (`examples/image_search/main.py`, `examples/image_search_colpali/main.py`) instantiate `transformers.CLIPModel` and `colpali_engine.ColPali` directly inside user `@coco.fn`. The framework only sees the resulting vectors. | No (BYO)     | Native multimodal *is achievable* (CLIP, ColPali shared-space embeddings) but the framework is uninvolved beyond schema declaration. |
| Audio    | `python/cocoindex/ops/litellm.py` ships `LiteLLMTranscriber`; wired in `examples/audio_to_text/main.py:24` as `LiteLLMTranscriber("whisper-1")`.                                            | **Yes**      | **Text-conversion fallback** (Whisper → transcript, then embed text). No native audio embedding model.    |
| Video    | None. `grep -ri "video\|mp4\|frame extraction\|whisper.*video\|ffmpeg" python/cocoindex/ rust/ops_text/` returns nothing in the framework. No example, no operator.                       | **No**       | Not supported. Would have to build entirely (frame extraction → image embedding + audio extraction → ASR + multimodal fusion). |
| PDF      | No first-party PDF operator. Examples (`examples/pdf_embedding/`, `examples/pdf_to_markdown/`) use `Docling` in user code.                                                                  | No (BYO)     | Text-conversion fallback.                            |

**Reading.** Cocoindex is **modality-neutral at the vector layer**
(`VectorSchema` + `MultiVectorSchema` accept any float-vector shape) and
**text-first at the operator layer**. For images and PDFs, "supporting
the modality" means "writing your own `@coco.fn` that calls a model and
declares vector targets." That is straightforward — the examples are
40–80 lines each — but it is *user code, not framework code*, and it
inherits the user's risk for model wrappers, GPU memory management, and
batching.

The CLI ships `COCOINDEX_RUN_GPU_IN_SUBPROCESS`
(`python/cocoindex/_internal/runner.py:172–199`) precisely to give those
user-defined embedders an isolation knob.

**Implication for our Goal 2.** Cocoindex satisfies the *plumbing*
(stable identity, vector targets, deletion propagation, batching,
reconciliation) but does **not** answer the modeling question for
non-text modalities. Adopting cocoindex still leaves us with the
"choose a multimodal embedder per modality" decision and the "wrap it
in a `@coco.fn`" plumbing. Video is a true gap — building it would be
real work.

---

## §C4. Embedding strategy and pluggability

* **Built-in embedder operators.** Two: `SentenceTransformerEmbedder`
  (`python/cocoindex/ops/sentence_transformers.py:25–100`) and
  `LiteLLMEmbedder` (`python/cocoindex/ops/litellm.py:29–150`). The
  latter is the breadth lever — through LiteLLM we get OpenAI, Voyage,
  Cohere, Bedrock, Ollama, vLLM, etc. for text embedding, and Whisper /
  comparable for transcription.
* **Protocol.** `python/cocoindex/resources/schema.py` declares
  `VectorSchema(size, dtype)` and `MultiVectorSchema` (used by ColPali);
  any object that produces matching vectors fits. The
  `VectorSchemaProvider` dunder interface is the formal extension
  point.
* **Batching is built-in.** The `@coco.fn.as_async(batching=True,
  max_batch_size=64)` decorator
  (`python/cocoindex/ops/sentence_transformers.py:94`) coalesces
  per-item calls into batches across concurrent components — important
  for both throughput and external-API cost.
* **Pluggability**: from the operator's perspective, an embedder is a
  callable that returns a vector of declared shape. Anything that
  satisfies that contract works. No registry, no plug-ins manifest;
  Python's import system is the registry.

**Verdict.** Embedding is **the most pluggable surface in the
framework**. We can plug in anything we want without touching cocoindex
internals.

---

## §C5. Source connectors relevant to indexit

Cross-checked against §C2 with file existence and connector kind.
("Read" = source-shaped iterator; "Write" = target-shaped reconciler.)

| Connector              | Read | Write | Indexit relevance                                                                |
| ---------------------- | ---- | ----- | -------------------------------------------------------------------------------- |
| `localfs`              | ✓    | ✓     | Direct fit for Sparkle on disk.                                                  |
| `postgres`             | ✓    | ✓     | Likely the central metadata store for our adoption. Pgvector for vectors.        |
| `google_drive`         | ✓    | —     | High value for S/Stream and shared knowledge ingestion.                          |
| `amazon_s3`            | ✓    | —     | Useful for archival mounts (L) and bulk imports.                                 |
| `oci_object_storage`   | ✓    | —     | Niche unless we adopt OCI; still good news that it's there.                      |
| `kafka`                | ✓    | ✓     | Useful for event-driven Stream ingestion.                                        |
| `qdrant`               | —    | ✓     | Strong vector target, ColPali/multivector capable.                                |
| `lancedb`              | —    | ✓     | Embedded vector store option (no service to run).                                 |
| `sqlite` (+ sqlite-vec)| —    | ✓     | Low-overhead local target; useful for laptop-scale pipelines.                    |
| `turbopuffer`          | —    | ✓     | Managed serverless vector option.                                                |
| `neo4j`                | —    | ✓     | Strong fit if we model Knowledge as a graph.                                     |
| `falkordb`             | —    | ✓     | Redis-based graph alt to Neo4j.                                                  |
| `surrealdb`            | —    | ✓     | Multi-model option; less mature target.                                          |
| `doris`                | —    | ✓     | Analytics target; unlikely primary fit for us.                                    |

**Notably missing for our purposes**: Notion, Obsidian/Markdown vault
(beyond plain localfs), Slack, GitHub issues/PRs, mailbox (IMAP),
generic webhook ingestion. These are the connectors we'd write in-house
or upstream.

---

## §C6. License, governance, bus factor

**License.** Apache-2.0 (`research/cocoindex/LICENSE`,
`Cargo.toml:15`). Permissive, compatible with downstream commercial /
proprietary use, includes patent grant. **No license risk.**

**Governance.** Single-organisation project (`cocoindex-io`). No
foundation, no public RFC process visible in the vendored repo. Roadmap
is communicated via release notes and the `v1` branch. Issues live on
GitHub; security via `security@cocoindex.io` (security.md §B12).

**Activity.** 270 commits in the last 90 days; 26 unique committers
in the last 90 days; ~1,400 commits in the last 12 months
(security.md §B12). Active and accelerating: v1.0.0 GA shipped after
50+ alphas, and v1.0.1/1.0.2/1.0.3 followed quickly.

**Bus factor (concern).** Top contributor (`Jiangzhou` / `Jiangzhou He`,
likely the same person) accounts for ≈629 commits over 12 months —
roughly **45 % of all commits**. Top three (Jiangzhou, LJ, George;
collapsing alias spellings) account for ≈75 %. This is a single-vendor
risk: if the lead author becomes unavailable, the project cadence
likely halts. We should:

1. Plan adoption assuming a 6–12 month responsiveness window for
   upstream PRs; not rely on rapid maintainer turn-around for blockers.
2. Maintain a fork or strong vendor copy so we can patch ourselves if
   needed.

**Maintainer responsiveness to security reports.** Not measurable from
the vendored snapshot; SECURITY.md commits to "as soon as we can"
without an SLA (security.md §B12).

---

## §C7. Concrete adaptation effort

Estimates assume one engineer familiar with Python + Rust enough to
read but not necessarily contribute to the core; calibrated to indexit's
requirements.

| Work item                                                                                          | Mode             | Estimate         |
| -------------------------------------------------------------------------------------------------- | ---------------- | ---------------- |
| Sparkle metadata layer (S/P/A/R/K/L/E registry + per-bucket policy + promotion API)                | Wrapper          | 1–2 dev-weeks    |
| Symlink containment patch for `localfs` connector (security.md F-1)                                | Fork or upstream | 1–3 days         |
| Default-disable telemetry in our wrapper (security.md F-2)                                         | Wrapper          | <1 day           |
| Add `cargo-deny` advisories + `pip-audit` to our CI                                                | CI               | 1 day            |
| Wrappers for image (CLIP) and PDF (Docling) embedders, mirroring the upstream examples              | User code        | 3–5 days         |
| ColPali / multivector path (if we want it)                                                          | User code        | 3–5 days         |
| Audio: thin wrapper around `LiteLLMTranscriber` to standardise our metadata fields                  | User code        | 1–2 days         |
| Video support (frame extraction + ASR + fusion) — only if we commit to video                        | New module       | 2–4 dev-weeks    |
| Cross-source dedup atop `entity_resolution` operator                                                | User code        | 1–2 dev-weeks    |
| Notion / Slack / GitHub / IMAP connectors                                                           | Per connector    | 1 dev-week each  |
| Operator runbook + runbook tests                                                                    | Docs             | 2–3 days         |

**Total floor (without video, with ~2 new connectors):** ~3–5 dev-weeks
to a usable indexit MVP atop cocoindex.

**Modes of contribution.**

* **Fork** — only required if upstream is slow on F-1 (symlink) and we
  cannot tolerate the risk in production. Even then, the fork lives at
  the connector layer; we don't need to fork the engine.
* **Wrapper** — primary mode. Most adaptation is "an indexit Python
  package that imports cocoindex and adds Sparkle semantics."
* **Upstream PR** — appropriate for symlink containment, cargo-deny
  integration, and any new generic-purpose connector.
* **Replace** — reserved for the case where we conclude during
  adoption that the engine is wrong for us. The exit cost is moderate
  (see below).

---

## §C8. Exit cost

* **Engine swap-out.** Pipelines are plain Python decorated with
  `@coco.fn`, calling into source/target connectors. Re-targeting at a
  different engine (LangChain, LlamaIndex, a hand-rolled scheduler)
  means rewriting the orchestration but **not** the embedding model
  choices, the vector schemas, or the target system contracts.
* **Data migration.** All persistent state lives in external systems we
  control (Postgres, Qdrant, …) plus the LMDB checkpoint. Migrating
  away from cocoindex preserves all indexed data; only the checkpoint
  is lost (and a full re-index would rebuild it).
* **License risk.** None — Apache-2.0.
* **Vendor risk.** Bus factor as noted in §C6; mitigated by the wrapper
  approach (we keep our domain logic outside cocoindex internals).

Exit cost is therefore **Low–Medium**: one-time orchestration rewrite,
no data migration, no license cleanup.

---

## §C9. Concrete recommendation

> **Adopt-with-changes.**
>
> Use cocoindex v1.0.x as the runtime engine and as the source/target
> connector library, behind an indexit wrapper that:
>
> 1. Adds the Sparkle taxonomy as a first-class metadata layer
>    (registry + promotion API).
> 2. Patches the `localfs` connector for symlink containment (F-1)
>    pending upstream PR.
> 3. Defaults `COCOINDEX_DISABLE_USAGE_TRACKING=1` for our processes
>    (F-2).
> 4. Adds `cargo-deny` and `pip-audit` to our CI (F-5).
> 5. Selects per-modality embedders explicitly (CLIP / ColPali /
>    Docling / Whisper) and wraps them as `@coco.fn` operators.
>
> Do **not** plan video support against cocoindex until/unless we
> commit to building it ourselves.
>
> Re-evaluate at the next major (`v1.1.x` or `v2.x`) if upstream lands
> a tenant-aware mode, a stable connector plug-in API, or a built-in
> image-embedding operator.

---

## §C10. References

* Component model & deletion propagation: `research/cocoindex/CLAUDE.md:88–124`,
  `research/cocoindex/rust/core/src/engine/execution.rs`.
* Embedder operators: `research/cocoindex/python/cocoindex/ops/{text,sentence_transformers,litellm}.py`,
  `research/cocoindex/python/cocoindex/resources/schema.py`.
* Image example (CLIP): `research/cocoindex/examples/image_search/main.py:24–67`.
* Image example (ColPali): `research/cocoindex/examples/image_search_colpali/main.py:24–60`.
* Audio example (Whisper via LiteLLM): `research/cocoindex/examples/audio_to_text/main.py:30–50`.
* Connector inventory: `research/cocoindex/python/cocoindex/connectors/` (15 modules at v1.0.3).
* License: `research/cocoindex/LICENSE`, `Cargo.toml:15`.
* Bus factor: see security.md §B12.
