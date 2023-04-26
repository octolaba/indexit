# CocoIndex v1.0.3 Applicability Review

## Metadata

- Agent: `gpt-5.5 high` (Codex)
- Pinned commit: `4432311228e4859201b457d3b6d978471692d0b1`
- Review mode: static source/documentation review only; upstream code was not run.

## Goal 1: Sparkle consistency

CocoIndex does not natively model Sparkle's S/P/A/R/K/L/E buckets. It gives us stable processing paths, target-state ownership, memoization, and connector abstractions; Sparkle semantics must be encoded by the downstream pipeline as explicit fields, target schemas, and source metadata.

Mapping:

| Sparkle bucket | Fit in CocoIndex                                                                                                                                                                                                                                                                                                              | Risk                                                                                                                                                                                                                    |
| -------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| S Stream       | Good as a source/live-feed concept. Localfs live mode, Kafka streams, and OCI live streams can represent incoming raw data (`research/cocoindex/python/cocoindex/connectors/localfs/_source.py:171-231`, `research/cocoindex/python/cocoindex/connectors/kafka/_source.py:1-8` @ `4432311228e4859201b457d3b6d978471692d0b1`). | Stream is not a built-in bucket; retention/triage state must be modeled by us.                                                                                                                                          |
| P Projects     | Possible through target rows keyed by project/source metadata.                                                                                                                                                                                                                                                                | No native time-bounded-outcome model or project lifecycle semantics.                                                                                                                                                    |
| A Areas        | Possible as metadata/tag fields.                                                                                                                                                                                                                                                                                              | Areas can collapse into generic resources unless our schema enforces distinction.                                                                                                                                       |
| R Resources    | Strong for reference indexing: text chunks, vectors, graph nodes, files.                                                                                                                                                                                                                                                      | Resource vs Knowledge distinction is not native.                                                                                                                                                                        |
| K Knowledge    | Possible only if downstream app records crystallization state, confidence, provenance, and user mastery markers.                                                                                                                                                                                                              | CocoIndex treats extracted knowledge graph facts and raw resources similarly unless schema separates them.                                                                                                              |
| L Legacy       | Possible through target deletion/archival fields or separate targets.                                                                                                                                                                                                                                                         | Archived vs deleted semantics must be designed; `App.drop()` deletes target states and internal DB state (`research/cocoindex/python/cocoindex/_internal/app.py:368-392` @ `4432311228e4859201b457d3b6d978471692d0b1`). |
| E Essentials   | Possible but risky. Essentials should be treated as explicit, protected source/category data with stricter permissions.                                                                                                                                                                                                       | No native identity/core-self boundary, permission model, or special handling.                                                                                                                                           |

## Source identity, metadata, ownership, permissions, dedup, sync, conflicts

What survives well:
- Stable per-item keys: `mount_each()` accepts keyed items and builds child paths from stable keys (`research/cocoindex/python/cocoindex/_internal/api.py:445-529` @ `4432311228e4859201b457d3b6d978471692d0b1`).
- Source path/object identity: S3 memo keys include bucket and relative path (`research/cocoindex/python/cocoindex/connectors/amazon_s3/_source.py:46-87` @ `4432311228e4859201b457d3b6d978471692d0b1`); OCI memo keys include namespace, bucket, and path (`research/cocoindex/python/cocoindex/connectors/oci_object_storage/_source.py:77-132` @ `4432311228e4859201b457d3b6d978471692d0b1`); Google Drive paths resolve to file IDs (`research/cocoindex/python/cocoindex/connectors/google_drive/_source.py:31-60` @ `4432311228e4859201b457d3b6d978471692d0b1`).
- Change detection: `FileLike.__coco_memo_state__` compares mtime and content fingerprint so unchanged content can remain memo-valid (`research/cocoindex/python/cocoindex/resources/file.py:178-202` @ `4432311228e4859201b457d3b6d978471692d0b1`).
- Target ownership/tracking: Rust stores target-state owner info and stable-path tracking (`research/cocoindex/rust/core/src/state/db_schema.rs:269-291` @ `4432311228e4859201b457d3b6d978471692d0b1`).
- Reconcile semantics: target diff helpers distinguish insert/upsert/replace/delete and support system-vs-user managed tracking records (`research/cocoindex/python/cocoindex/connectorkits/statediff.py:101-146`, `research/cocoindex/python/cocoindex/connectorkits/statediff.py:149-187` @ `4432311228e4859201b457d3b6d978471692d0b1`).

What is weak or missing:
- Permissions and ownership from sources are mostly not preserved. Google Drive lists `id`, `name`, `mimeType`, `size`, and `modifiedTime`, not ACLs/owners (`research/cocoindex/python/cocoindex/connectors/google_drive/_source.py:184-213` @ `4432311228e4859201b457d3b6d978471692d0b1`).
- Google Drive `items()` keys by name path, not file ID (`research/cocoindex/python/cocoindex/connectors/google_drive/_source.py:255-261` @ `4432311228e4859201b457d3b6d978471692d0b1`). Duplicate names under different folders or renamed files can collide or distort source identity unless downstream overrides keying.
- Conflict state is not a first-class cross-source concept. Target handlers compare desired vs previous tracking records, but semantic conflicts between two sources claiming the same Sparkle object must be modeled separately.
- Deduplication exists as a target/app concern, not as a cross-source identity service. Entity resolution is available as optional ops, but it is not wired into every connector by default (`research/cocoindex/pyproject.toml:93-98` @ `4432311228e4859201b457d3b6d978471692d0b1`).

## Goal 2: multimodal semantic indexing

CocoIndex can process multimodal data because source files are byte-oriented and transforms are arbitrary Python. It is not, however, a modality-aware retrieval system out of the box.

Per modality:

| Modality            | Evidence                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    | Assessment                                                                                                                      |
| ------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| Text                | Built-in recursive and separator splitters, code language detection, sentence-transformer and LiteLLM text embedders (`research/cocoindex/python/cocoindex/ops/text.py:19-84`, `research/cocoindex/python/cocoindex/ops/text.py:120-180`, `research/cocoindex/python/cocoindex/ops/sentence_transformers.py:25-183`, `research/cocoindex/python/cocoindex/ops/litellm.py:29-164` @ `4432311228e4859201b457d3b6d978471692d0b1`).                                                                                                             | First-class enough for RAG/text indexing.                                                                                       |
| Image               | Examples use CLIP image embeddings and query text embeddings into Qdrant (`research/cocoindex/examples/image_search/main.py:1-8`, `research/cocoindex/examples/image_search/main.py:42-63`, `research/cocoindex/examples/image_search/main.py:77-116` @ `4432311228e4859201b457d3b6d978471692d0b1`). ColPali example stores multi-vector image embeddings (`research/cocoindex/examples/image_search_colpali/main.py:1-8`, `research/cocoindex/examples/image_search_colpali/main.py:76-139` @ `4432311228e4859201b457d3b6d978471692d0b1`). | Supported by examples and generic vector schemas, not by a built-in image operator.                                             |
| Audio               | LiteLLMTranscriber reads audio bytes and returns transcript text (`research/cocoindex/python/cocoindex/ops/litellm.py:167-223` @ `4432311228e4859201b457d3b6d978471692d0b1`). Audio example transcribes files to Postgres text rows (`research/cocoindex/examples/audio_to_text/main.py:1-7`, `research/cocoindex/examples/audio_to_text/main.py:49-91` @ `4432311228e4859201b457d3b6d978471692d0b1`).                                                                                                                                      | Audio is reduced to ASR text; no native audio embedding path in core.                                                           |
| Video               | README describes videos as context sources (`research/cocoindex/README.md:18-22` @ `4432311228e4859201b457d3b6d978471692d0b1`) and conversation examples discuss YouTube audio/transcription metadata (`research/cocoindex/examples/conversation_to_knowledge/spec.md:44-60` @ `4432311228e4859201b457d3b6d978471692d0b1`).                                                                                                                                                                                                                 | Video handling is workflow/example-level, usually via audio extraction/transcription and metadata, not native video embeddings. |
| PDF/document images | PDF examples convert to markdown or process rendered images through vision-model tooling (`research/cocoindex/examples/patient_intake_extraction_dspy/main.py:42-55`, `research/cocoindex/examples/patient_intake_extraction_baml/main.py:17-18` @ `4432311228e4859201b457d3b6d978471692d0b1`).                                                                                                                                                                                                                                             | Mixed: either text extraction/markdown fallback or direct vision-model extraction in examples.                                  |

Native multimodal representations:
- Native image embeddings: CLIP and ColPali examples use image bytes directly before writing vectors (`research/cocoindex/examples/image_search/main.py:57-63`, `research/cocoindex/examples/image_search_colpali/main.py:76-83` @ `4432311228e4859201b457d3b6d978471692d0b1`).
- Native multi-vector schema: `MultiVectorSchema` supports late-interaction/multi-vector stores (`research/cocoindex/docs/src/content/docs/common_resources/vector_schema.mdx:111-121` @ `4432311228e4859201b457d3b6d978471692d0b1`).
- Text fallbacks: audio transcriber reduces audio to text (`research/cocoindex/python/cocoindex/ops/litellm.py:193-220` @ `4432311228e4859201b457d3b6d978471692d0b1`); PDF-to-markdown/text examples reduce documents to text (`research/cocoindex/examples/pdf_embedding/main.py:60-63`, `research/cocoindex/examples/pdf_embedding/main.py:119-142` @ `4432311228e4859201b457d3b6d978471692d0b1`).

## Embedding/model strategy and pluggability

Embedding is pluggable by ordinary Python transforms plus schema providers. Built-ins include:
- `SentenceTransformerEmbedder`, with lazy model load, GPU runner batching, memoized `embed()`, and vector schema provider (`research/cocoindex/python/cocoindex/ops/sentence_transformers.py:25-183` @ `4432311228e4859201b457d3b6d978471692d0b1`).
- `LiteLLMEmbedder`, with provider kwargs and memoized single-text embed (`research/cocoindex/python/cocoindex/ops/litellm.py:29-164` @ `4432311228e4859201b457d3b6d978471692d0b1`).
- Arbitrary custom models, because transforms are Python functions and vector schema can be supplied explicitly (`research/cocoindex/docs/src/content/docs/common_resources/vector_schema.mdx:96-109` @ `4432311228e4859201b457d3b6d978471692d0b1`).

This is flexible but does not enforce modality-aware retrieval policy. Downstream must route text/image/audio/video to appropriate transforms, vector spaces, and query strategies.

## Existing source connectors relevant to us

Source connectors:
- Local filesystem source with live watch (`research/cocoindex/python/cocoindex/connectors/localfs/_source.py:68-168`, `research/cocoindex/python/cocoindex/connectors/localfs/_source.py:171-260` @ `4432311228e4859201b457d3b6d978471692d0b1`).
- Amazon S3 source (`research/cocoindex/python/cocoindex/connectors/amazon_s3/_source.py:1-19`, `research/cocoindex/python/cocoindex/connectors/amazon_s3/_source.py:247-260` @ `4432311228e4859201b457d3b6d978471692d0b1`).
- OCI Object Storage source with optional live stream (`research/cocoindex/python/cocoindex/connectors/oci_object_storage/_source.py:1-13`, `research/cocoindex/python/cocoindex/connectors/oci_object_storage/_source.py:246-280` @ `4432311228e4859201b457d3b6d978471692d0b1`).
- Google Drive source (`research/cocoindex/python/cocoindex/connectors/google_drive/_source.py:1-5`, `research/cocoindex/python/cocoindex/connectors/google_drive/_source.py:232-261` @ `4432311228e4859201b457d3b6d978471692d0b1`).
- Postgres source (`research/cocoindex/python/cocoindex/connectors/postgres/_source.py:1-5`, `research/cocoindex/python/cocoindex/connectors/postgres/_source.py:130-227` @ `4432311228e4859201b457d3b6d978471692d0b1`).
- Kafka source (`research/cocoindex/python/cocoindex/connectors/kafka/_source.py:1-8` @ `4432311228e4859201b457d3b6d978471692d0b1`).

Target connector families include Postgres, SQLite, LanceDB, Qdrant, Turbopuffer, Neo4j, FalkorDB, SurrealDB, Doris, Kafka, and local filesystem. The optional dependency groups expose most target families (`research/cocoindex/pyproject.toml:71-126` @ `4432311228e4859201b457d3b6d978471692d0b1`), while concrete package exports show target modules for Postgres, SQLite, Qdrant, and local filesystem (`research/cocoindex/python/cocoindex/connectors/postgres/__init__.py:1-6`, `research/cocoindex/python/cocoindex/connectors/sqlite/__init__.py:1-4`, `research/cocoindex/python/cocoindex/connectors/qdrant/__init__.py:1-4`, `research/cocoindex/python/cocoindex/connectors/localfs/__init__.py:1-10` @ `4432311228e4859201b457d3b6d978471692d0b1`).

## License

The package declares Apache-2.0 license (`research/cocoindex/pyproject.toml:22-24` @ `4432311228e4859201b457d3b6d978471692d0b1`), and the GitHub repository page also identifies Apache-2.0 (<https://github.com/cocoindex-io/cocoindex>). This is compatible with downstream commercial use, subject to normal notice/patent obligations.

## Maintainer activity, governance, and bus factor

Activity is high. The repository page shows 8.5k stars, 628 forks, 197 releases, and `v1.0.3` as latest on May 5, 2026 (<https://github.com/cocoindex-io/cocoindex>). Local git metadata at the pinned submodule shows 270 commits in the last 90 days before this report and many tags around v1.0.0-v1.0.3. However, the recent commit distribution is concentrated: one author accounts for most recent commits, with a broader long-tail contributor base. This is a moderate bus-factor risk despite strong public activity.

Governance artifacts present in the repo include code of conduct, contributing guide, and security policy (`research/cocoindex/CODE_OF_CONDUCT.md`, `research/cocoindex/CONTRIBUTING.md`, `research/cocoindex/.github/SECURITY.md` @ `4432311228e4859201b457d3b6d978471692d0b1`). Security-process maturity appears to be improving via GitHub Secure Open Source Fund participation and stated CodeQL/secret scanning/dependency review work (<https://cocoindex.io/blogs/cocoindex-joins-security-github-secure-open-source-fund/>).

## Concrete adaptation effort

Recommended adoption path: **wrapper plus selective upstream contributions**.

Required wrapper work:
- Define a canonical `SparkleItem` schema with bucket, source ID, source type, source URI, source-native ID, source path, owner, ACL summary, timestamps, content hash, modality, embedding space, conflict status, and tombstone/archive status.
- Normalize connector keys. Use source-native IDs where available; do not use Google Drive name path as the only key (`research/cocoindex/python/cocoindex/connectors/google_drive/_source.py:255-261` @ `4432311228e4859201b457d3b6d978471692d0b1`).
- Add modality routing: text splitter/text embedder; image embedder/multi-vector image path; audio ASR plus optional native audio embedding; video frame/audio/metadata decomposition.
- Add permission and ownership ingestion for Google Drive/S3/OCI/Postgres/Kafka where source APIs expose it.
- Add dedup/entity resolution as an explicit stage with traceable source clusters.
- Add connector hardening for localfs symlinks and SQL identifiers before exposing user-configured sources/targets.

Effort estimate:
- Proof of concept: 1-2 weeks for localfs/S3/text/image with Sparkle fields.
- Product-grade MVP: 4-8 weeks for permissions, conflict state, dedup, multimodal routing, and security hardening.
- Broad connector coverage: 2-4 additional months depending on permission models and target stores.

## Exit cost

Exit cost is moderate. User pipelines are ordinary Python functions, and target stores are standard external databases/vector stores. The main lock-in is CocoIndex's LMDB internal state and target-state reconciliation contract. If the project stalls, we can keep target data and replace the orchestration layer, but we would lose incremental memoization, stable-path tracking, and connector-specific reconciliation behavior. A wrapper that keeps Sparkle metadata independent from CocoIndex internals lowers exit cost.

## Final recommendation

**Adopt-with-changes.**

CocoIndex is a strong candidate as the incremental execution substrate for heterogeneous indexing. It should not be adopted as the full product data model. Sparkle requires a strict taxonomy/schema layer, source permission preservation, conflict tracking, and cross-source deduplication that CocoIndex does not provide natively. Multimodal support is promising because arbitrary Python transforms and vector schemas can express CLIP, ColPali, text embeddings, and ASR workflows, but modality policy and native audio/video handling remain downstream responsibilities.
