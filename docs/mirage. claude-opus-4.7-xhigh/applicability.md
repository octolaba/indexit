# Mirage v0.0.1 — Applicability for indexit

> Run: `claude-opus-4.7-xhigh` · Pinned ref: tag `v0.0.1`, commit
> `8b99fb9247ecb40725d4718bac58e3bb230aad34` · Submodule:
> `research/mirage/`

This report judges Mirage strictly against the two indexit goals
(`CLAUDE.md` §1):
**Sparkle consistency** (Goal 1) and **multimodal semantic indexing**
(Goal 2). Generic praise/criticism that does not bear on those goals is
omitted.

The headline answer is set up-front: **Mirage is not an indexer. It is a
unified VFS for AI agents.** The applicability question therefore
reduces to: "could mirage serve as a *connector layer* underneath an
indexer that we build?" — which is a fairer question than "does mirage
solve our indexing problem?" (it does not).

---

## 1. Sparkle (Goal 1) — fit assessment

### 1.1. Bucket-by-bucket mapping

The Sparkle taxonomy classifies *items* into S/P/A/R/K/L/E. Mirage
classifies nothing — it exposes *paths*. So the Sparkle question becomes
"can the indexer that consumes mirage preserve the distinctions Sparkle
needs?".

| Bucket | Maps onto a Mirage concept? | Loss / gain |
| --- | --- | --- |
| **S** Stream | Yes — every remote `Resource` (Slack, Email, Discord, Telegram, GitHub Issues, Linear) is naturally a Stream source mounted under `/<prefix>/` | Mirage does not deduplicate cross-source streams; same item appearing in Slack DM and email is two different paths |
| **P** Projects | Out of scope for mirage | The indexer must add this layer; mirage carries no project lifecycle field |
| **A** Areas | Out of scope for mirage | Same as above |
| **R** Resources | Indirectly — `GDocsResource`, `GSheetsResource`, `GDriveResource`, `NotionResource`, `LinearResource` provide Resource-flavoured backends | Filesystem flattening loses Notion's block hierarchy and GDoc revision history beyond what `FileStat.extra` carries |
| **K** Knowledge | **No mapping.** "Crystallised expertise" is a *user-internalised* state, not a source feature | Indexer-side concern; mirage is neutral |
| **L** Legacy | No archival semantics in mirage | Indexer-side concern |
| **E** Essentials | No identity-layer concept | Indexer-side concern |

**Verdict on the taxonomy.** Mirage cleanly serves S and (loosely) R as
*source* layers. P/A/K/L/E are problems for the indexer that *consumes*
mirage. There is no friction with the taxonomy because mirage refuses to
model bucket membership at all — the boundary stays clean.

### 1.2. Source identity preservation

Mirage preserves **backend identity per mount prefix**: `/s3/...`,
`/slack/...`, `/notion/...`. After `ws.copy()` the prefix is the same
even if the underlying resource is re-instantiated
(`research/mirage/python/mirage/workspace/workspace.py:310-333`). For
remote backends, source identity at the *item* level is the path within
that mount — and that path is whatever the resource invents to flatten
the upstream onto a filesystem. Examples:

* **GitHub.** `(/owner/repo, ref)` is encoded into the resource
  constructor (`research/mirage/python/mirage/resource/github/github.py:36-51`).
  The mount itself is `/github/`; the per-item identity is the relative
  tree path. Stable across pulls because the upstream tree SHA is in
  `IndexEntry.id`.
* **Notion.** Notion blocks become files; block IDs survive in the
  `_meta` / `extra` shape but the canonical handle is the path.
* **Slack.** Channels become folders, messages become files (e.g.
  `/slack/general/2026-04-29.json`). Thread IDs survive in the JSON
  payload, not in the path.
* **Email.** Mailboxes become folders, messages files. Per-message
  identity is whatever path the resource picks (typically the IMAP UID).

**Implication for Sparkle.** The indexer that wraps mirage can rely on
the path being stable enough to use as a key for its own dedup/lineage
layer, but cross-source dedup (same article in Slack thread + Notion +
email) has to come from content fingerprinting **above** mirage.

### 1.3. Metadata preservation

`FileStat` (`research/mirage/python/mirage/types.py:39-47`) carries
`name/size/modified/fingerprint/type/extra:dict`. The VFP-flavoured
`FileStat` (`research/mirage/python/mirage/vfp/types.py:77-87`) is
slightly richer with `meta:dict` aliased to `_meta` and a dedicated
`type` enum. Both are *thin*: any per-resource richness has to live in
the `extra`/`meta` dict.

In practice this means:

| Source | What survives in `FileStat.extra` (or analogue) | What is lost |
| --- | --- | --- |
| GDocs | document ID, mime type, modified time | revision history, comments, suggestion mode, ACLs |
| Slack | message ts, thread_ts (if encoded) | reactions, edit history, user role |
| Notion | block ID, parent ID | block-tree relations, formulas, rollups |
| Linear | issue ID, status | parent project, cycle, assignee history |
| GitHub | tree-entry SHA, size | issue comments (the GitHub resource is repo-tree only at v0.0.1 — issue/PR mounts come later per `research/mirage/docs/plans/`) |
| Email | UID | thread relations (X-Refs / In-Reply-To not normalised), spam labels |

**Sparkle implication.** If our indexer needs *any* of the lost
metadata, mirage will require either custom commands per resource (its
public extension surface — see architecture §7) or post-hoc enrichment
above the filesystem layer.

### 1.4. Permissions / ACL surfacing

Mirage's permission model is **mount-mode level**: `MountMode` in
{READ, WRITE, EXEC} (`research/mirage/python/mirage/types.py:50-54`).
There is no user model, no per-item ACL surfacing, no
"propagate-upstream-ACL" hook. The HTTP daemon has no auth (security
§3.1).

**Sparkle implication.** A Sparkle-aware indexer that needs to honour
upstream permissions ("don't index files only Bob can see") cannot
delegate to mirage. It must consult the upstream itself, or run mirage
as the same identity for which it is doing the indexing — i.e., one
mirage instance per identity.

### 1.5. Deduplication

Cache is **path-keyed** (`research/mirage/python/mirage/workspace/workspace.py:374-402`).
Two paths pointing to the same upstream object cache twice.
`fingerprint()` per resource (e.g.
`research/mirage/python/mirage/resource/s3/s3.py:106-111` returns S3
ETag) lets `ConsistencyPolicy.ALWAYS` re-stat for freshness, but
fingerprints are not used for cross-resource dedup.

**Sparkle implication.** Dedup must happen above mirage. This is
acceptable — most indexers do their own content dedup anyway — but it
means mirage cannot itself answer "is this the same thing in two
different sources?".

### 1.6. Sync / update / conflict semantics

* **Pull on read.** Mirage never *pushes* from upstream. There is no
  watcher, no webhook handler, no event subscription.
* **Index TTL.** Default 600 s for the directory listing cache
  (`research/mirage/python/mirage/resource/base.py:37`). After TTL, the
  next `readdir` re-fetches.
* **Write coherence.** Writes to a remote-backed mount invalidate the
  file cache for the path and the index cache for the parent directory
  (`research/mirage/python/mirage/workspace/workspace.py:399-445`).
* **Conflicts.** None modelled. If two agents write the same path
  concurrently the upstream's last-writer-wins applies. No CRDT, no
  vector clock, no optimistic-lock primitives.

**Sparkle implication.** An indexer that wants real-time consistency
must drive mirage with `ConsistencyPolicy.ALWAYS` and accept the
per-dispatch stat round-trip; for a reactive index (incremental update
on upstream changes), mirage offers nothing — the indexer must wire its
own webhooks / pollers.

### 1.7. Net Sparkle assessment

* **Where Mirage helps:** as a **uniform `read_bytes` / `readdir` /
  `stat` interface** across 22 source kinds, with a small file-cache
  layer underneath. That alone removes ~30% of the boilerplate of
  building an indexer.
* **Where Mirage doesn't:** classification, dedup, permission-aware
  surfacing, push-based sync, and any actual *index* that supports
  search.

The Sparkle taxonomy is **not contradicted** by mirage; it simply isn't
addressed. Compatibility is "neutral", not "supportive".

---

## 2. Multimodal semantic indexing (Goal 2) — fit assessment

### 2.1. Native multimodal vs. text-only fallbacks

**The product carries no embedding model, no vector store, no
multimodal pipeline.** Verified by inspection of
`research/mirage/python/pyproject.toml:36-129`: no `sentence-transformers`,
no `clip`, no `chroma`, no `qdrant`, no `pgvector`, no `openai-embeddings`
helper, no `cohere`, no `voyageai`. The optional `audio` extra brings
`sherpa-onnx` (offline ASR), `av`, and `tinytag`; that is the *only*
non-text modality with anything resembling extraction logic in mirage
itself, and it is a text-conversion fallback (audio → transcript).

| Modality | Mirage built-in path | Native multimodal? |
| --- | --- | --- |
| Text (.txt/.md/.py/.json/.yaml/.csv/.tsv/.jsonl) | First-class. Categorised in `EXTENSION_MAP` (`research/mirage/python/mirage/resource/filetype.py:17-37`); shell helpers (`grep`, `jq`, `sed`, `wc`, `head`, `tail`, `cut`, `nl`, `tr`, `uniq`, `sort`) operate on bytes | n/a — text |
| Structured tabular (Parquet, ORC, Feather, HDF5) | Optional via `parquet`/`hdf5` extras (pandas + pyarrow + h5py); `commands/builtin/jq_helper.py` and per-resource helpers do row-wise ops | Not embedded, just queried |
| Image (PNG / JPEG / GIF) | Categorised in `EXTENSION_MAP`; `pillow` is in core deps; PDFs use `pypdfium2` to rasterize | **No native multimodal embedder.** Reads are byte-level |
| PDF | Optional `pdf` extra (pypdfium2, pillow). No OCR pipeline observed | Treated as a binary blob in core ops |
| Audio | Optional `audio` extra; `commands/local_audio/disk/ram/s3` provides per-mount audio commands; `sherpa-onnx` ships ASR models | **Text-conversion fallback** (ASR transcript) |
| Video | Not handled; `av` is included only for audio container parsing | **No support** |

The README markets the system as a *unified abstraction* over services,
not as a multimodal search engine. There is no claim to be one.

### 2.2. Modality-specific extraction / embedding / indexing / retrieval

* **Extraction.** Per-modality extraction exists for audio (`commands/local_audio/`)
  and PDFs (via `pypdfium2`). Image OCR, video transcript, image
  caption — **absent**.
* **Embedding.** **None.** There is no embedder anywhere in the code
  base.
* **Indexing.** Only directory metadata caching, not content indexing
  (architecture §6).
* **Retrieval.** Search-pushdown to upstream APIs where a resource
  supports it (Slack search via the Slack API, GitHub via search API);
  otherwise byte-streaming through `grep`/`rg`/`jq`. There is no
  vector retrieval, no ANN, no rerank.

### 2.3. Embedding strategy and pluggability

There is **no embedding strategy**. The closest concept the codebase
exposes that an indexer could exploit is:

* The **public `command` extension surface** — register a custom verb
  like `embed` per resource, push the bytes through your embedder,
  write the vector somewhere
  (`research/mirage/python/mirage/commands/registry.py`).
* The `BaseResource` hook for custom backends — implement an "embedder
  resource" that pretends to be a filesystem mount but emits embedding
  records via `Workspace.execute` / `Ops`
  (`research/mirage/python/mirage/resource/base.py`).

Both are **possible but ad-hoc**. Mirage is not designed for either.

### 2.4. Net multimodal assessment

* Text + structured: well covered as a **read** layer.
* Image / PDF: byte-level reads only; no OCR / no captioner / no
  image-embedder.
* Audio: ASR via `sherpa-onnx` (text-conversion fallback).
* Video: no support.
* Embeddings / vector search: **absent.**

For Goal 2 specifically, mirage has roughly the same value as `boto3`:
it gets the bytes to you reliably. The semantic and multimodal layers
must be built above it.

---

## 3. Source connectors relevant to indexit

| Connector | Mirage version | Indexit relevance |
| --- | --- | --- |
| RAM, Disk | core | Local sandbox; useful for staging |
| S3, R2, GCS, OCI, Supabase Storage | extras | Bulk content store |
| GDrive, GDocs, GSheets, GSlides | extras | High-value Sparkle Stream |
| Gmail, Email (IMAP/SMTP) | extras | High-value Sparkle Stream |
| Slack, Discord, Telegram | extras | High-value Sparkle Stream |
| GitHub, GitHub CI | core / extras | Knowledge / Resources |
| Linear, Trello, Notion | core / extras | Projects / Areas / Knowledge |
| MongoDB, Postgres | extras | Internal data sources |
| SSH | extras | Generic remote disk |
| Redis | extras | Cache / store backend |
| Langfuse, Paperclip | core / extras | Niche / observability |

22 backends covers most of the connectors a Sparkle-style index would
want. The **breadth** is mirage's strongest selling point relative to
hand-rolling a connector layer.

---

## 4. License

* **Apache-2.0** for both Python and TypeScript packages
  (`research/mirage/python/pyproject.toml:7`,
  `research/mirage/LICENSE`).
* Compatible with **proprietary downstream**, including the future
  indexit product code that will live in a separate repository.
* Notice / attribution requirements are the standard Apache-2.0
  obligations — cheap to satisfy.

---

## 5. Maintainer activity, governance, bus factor

* **Single maintainer.** `pyproject.toml:9-11` lists
  `Zecheng Zhang <zecheng@strukto.ai>`. The security email is the same
  individual.
* **Governance.** No published RFC/contrib structure beyond
  `CONTRIBUTING.md` (encourages issues/discussions before non-trivial
  work, AI-assisted contributions allowed if reviewed).
* **History.** Three commits at the pin
  (`924ec49 Initial public release`, `5eb17c3 Update`, `8b99fb9 Update`).
  Single tag `v0.0.1`, alpha. No release cadence to extrapolate from.
* **Bus factor.** **1.** Backed by the strukto.ai company — lower the
  factor accordingly if the company turns over.
* **Discord / docs.** Active marketing surface (`docs.mirage.strukto.ai`),
  Discord invite. Implies active development outside of the public
  repo's git log; the public repo only carries shaped releases at this
  stage.

---

## 6. Adaptation effort estimate

Three plausible integration shapes, in order of cost:

| Shape | What we'd do | Effort |
| --- | --- | --- |
| **Wrapper / consumer** (recommended baseline) | Use `Workspace` as a library, call `read_bytes` / `readdir` / per-resource search-pushdown commands from our indexer. Build embeddings, vector store, Sparkle classifier on top. Bring our own auth model. | **Low–Medium**: 1–2 weeks for an MVP that pulls from 3–4 mounts; per-modality extractors are the long tail |
| **Plugin / fork** | Add an "embed" command and a vector-store cache as new mirage extension surfaces; keep mirage's daemon as the I/O process. | **Medium**: 3–6 weeks. We'd own a fork until the upstream design stabilises |
| **Upstream contribution** | Land a "search-pushdown protocol" + "embedder resource" PR upstream. The plans dir already drafts a `search-pushdown-multipath` design (`research/mirage/docs/plans/2026-04-26-search-pushdown-multipath.md`). | **High**: needs maintainer alignment, alpha surface stability, and review of CLA / governance |

**Exit cost**, should mirage stall or pivot, is a function of how
deeply we lean on it:

* If we use mirage only as a connector library (Shape 1): **Low**.
  Replacing the layer means rewriting per-source `read_bytes`/`stat`
  glue — irritating but bounded; ~2 weeks per backend cluster.
* If we run the daemon (Shape 1.5) and rely on `Workspace.execute`:
  **Medium**. The shell-pipeline layer (parser + executor + commands)
  is non-trivial to replicate.
* If we fork (Shape 2): **High**, because we own a tree of 25k LoC
  Python + sibling TS we did not write.

---

## 7. Operational red flags for our context

These come from the security review (`security.md`), focused on what
matters if we *adopt* mirage:

1. **No daemon auth (security §3.1).** Either rebuild the runtime
   inside our own service that wraps `Workspace` directly — bypassing
   the daemon — or land an auth dependency upstream before exposing the
   daemon to anything.
2. **`native: true` shell on host (security §3.2).** Disable in our
   wrapper; never accept it from agent tool calls.
3. **Snapshot-load traversal (security §3.4).** Block the
   `POST /v1/workspaces/load` route or patch `DiskResource.load_state`
   before trusting persistence.
4. **SSH host-key default (security §3.5).** Override
   `SSHConfig.known_hosts` to `~/.ssh/known_hosts` in any config we
   ship.
5. **Single-tenant design.** The daemon, FUSE bridge, observer, and
   workspaces all assume one user; we'd run one daemon per tenant or
   use the SDK directly per-process.

None of these are blockers for *consumer-mode* use, but each must be
factored into the integration plan.

---

## 8. Strengths to keep in mind

* **Breadth of connectors.** 22 backends covers most Sparkle Stream
  sources. Building this from scratch is a lot of months.
* **Familiar UX for agents.** The "agents already speak bash" thesis is
  genuinely useful; if our future indexer surfaces a search UI to an
  agent, mirage's `Workspace.execute` is a natural sandbox.
* **Cache + freshness are correct.** The path-keyed file cache and the
  TTL'd index cache are simple, predictable, and Redis-backed for
  multi-replica deployments.
* **Snapshot/clone primitives.** The serialisable workspace is a nice
  building block for "freeze the state before a destructive change",
  even if v0.0.1's tar exporter has the §3.4 / §3.8 issues.
* **VFP capability declarations.** Even unimplemented, the type surface
  in `vfp/` is a thoughtful artefact: it tells you what mirage thinks
  *should* be the contract between an LLM tool host and the VFS, and
  matches the operations we'd want to advertise from any indexer-on-top.
* **Cross-language parity.** Python + TS implementations means embed
  paths in both Node services and Python pipelines.

---

## 9. Concrete adoption recipe (if we monitor → adopt)

1. **Wrap, don't host.** Embed `Workspace` in our indexer service via
   `from mirage import Workspace`. Skip the daemon entirely until
   security §3.1 is fixed upstream.
2. **Lock down resources.** Build a small allowlist of resources we
   accept (S3, GitHub, Slack, Notion, GDocs, Email — depending on what
   indexit pilots). Drop the file-path branch of `load_backend_class`
   in our deployment by patching or by never calling it.
3. **Pin transitive deps.** Use `uv lock --upgrade-package mirage-ai`
   per release; pin SDK extras explicitly. Run our own SCA over the
   resolved tree.
4. **Wrap `execute` with a policy gate** that strips `native=True` and
   sanitises the agent-supplied command before passing it through.
5. **Build the indexer above mirage.** Use mirage purely for
   `readdir`/`stat`/`read_bytes`. Run our own embedder, our own vector
   store, our own Sparkle classifier. Keep mirage as a *source layer*.
6. **Watch upstream.** Track the issues for: daemon auth, snapshot
   hardening, search-pushdown protocol, audio/image extraction
   surface. Re-evaluate at the next minor release.

---

## 10. Final recommendation

### **Verdict: monitor**

* **Reasoning.** Mirage is a competent VFS layer for AI agents but a
  **non-fit for the indexing problem indexit is trying to solve**. It
  doesn't index, it doesn't embed, it doesn't classify, and it doesn't
  do multimodal anything other than ASR. Adopting it as our indexer
  would force us to build the indexer above it anyway. Adopting it as
  a *connector layer* is feasible — the cache + freshness model is
  correct and the breadth of backends is genuinely valuable — but
  v0.0.1 is alpha-quality with several security issues that must be
  fixed before exposing any HTTP surface, and our exit cost stays low
  as long as we use it via the SDK rather than the daemon.
* **Why not "adopt-with-changes" right now.** The daemon's auth gap,
  the snapshot-load traversal, the SSH host-key default, and the
  three-commit history place mirage on the wrong side of "trust this
  enough to depend on it for a product feature". Bus-factor 1 + alpha
  + open critical-severity findings = monitor.
* **Why not "reject".** The architecture is fundamentally sound, the
  breadth of connectors is hard to replicate, the VFP type surface
  shows good taste, and the maintainer's pace + Apache-2.0 license +
  TypeScript parity would all be *helpful* if the security gaps close.
  Re-evaluate at v0.1.x.
* **Re-evaluation triggers.**
  1. Daemon auth landing in a tagged release.
  2. `DiskResource.load_state` traversal closed.
  3. SSH host-key default-on.
  4. A second maintainer or visible contribution cadence.
  5. Search-pushdown / embedder extension surfaces stabilised.

### Adoption shape if we eventually flip to *adopt-with-changes*

* Use `Workspace` SDK in our process. Skip the daemon.
* Vendor mirage as a git submodule pinned to a tag.
* Wrap `execute` with a policy gate.
* Allowlist the resources we trust.
* Watch the security advisory channel.

---

## 11. §4.3 question checklist (explicit answers)

| §4.3 question | Answer (location) |
| --- | --- |
| Sparkle mapping | §1 above. Mirage is neutral; it serves S/R but does not classify |
| Non-text modalities | §2 above. **Bolted-on text fallbacks (audio → ASR) at most, no native multimodal** |
| Source identity, metadata, permissions, dedup, sync | §1.2–1.6 above |
| Native vs. fallback per modality | §2.1 / §2.2 above |
| Embedding strategy | §2.3 above. **None in v0.0.1** |
| Existing connectors relevant to us | §3 above (22 backends) |
| License | Apache-2.0 — §4 |
| Maintainer activity / governance / bus factor | §5 |
| Adaptation effort: fork / plugin / wrapper / contribution | §6 |
| Final recommendation with reasoning | §10 |
