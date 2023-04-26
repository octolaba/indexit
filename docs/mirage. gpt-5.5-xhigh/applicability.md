# Mirage Applicability Review

All citations refer to `research/mirage` at pinned upstream commit `8b99fb9247ecb40725d4718bac58e3bb230aad34` (`v0.0.1`).

## Applicability Summary

Mirage is useful as a heterogeneous source access layer, but it does not meet `indexit`'s two core goals as a product-ready component. It can preserve coarse source identity through mount paths and backend-specific metadata, but it does not model Sparkle categories, source permissions, deduplication, sync conflicts, native multimodal embeddings, or semantic retrieval. Final recommendation: **reject** as the core index/search engine; monitor as a possible connector/VFS substrate.

## Sparkle Fit

Mirage's closest native concept to Sparkle structure is the mount prefix. A resource maps an external system into Mirage and a mount attaches it to a path such as `/data`, `/s3`, or `/github` (`research/mirage/docs/home/concepts.mdx:36`-`research/mirage/docs/home/concepts.mdx:44`). `MountRegistry` then routes by longest prefix (`research/mirage/python/mirage/workspace/mount/registry.py:26`-`research/mirage/python/mirage/workspace/mount/registry.py:32`).

That is not enough for Sparkle. Sparkle buckets are semantic and lifecycle categories, while Mirage paths are source/resource addresses. Forcing Sparkle into Mirage paths would mix taxonomy with source identity and would fail once one source contains items from multiple buckets.

| Sparkle bucket | Mirage mapping                                                                                        | Fit                                                      |
| -------------- | ----------------------------------------------------------------------------------------------------- | -------------------------------------------------------- |
| S - Stream     | Could mount inbox-like sources such as Gmail, Slack, Discord, Telegram, Email, or raw object storage. | Partial; no native inbox/triage state.                   |
| P - Projects   | Could represent project folders, GitHub repos, Linear issues, or Notion pages.                        | Partial; no project outcome/time-box metadata.           |
| A - Areas      | Could represent long-lived folders or SaaS spaces.                                                    | Weak; no distinction between areas and essentials.       |
| R - Resources  | Could represent topic folders, cloud files, docs, and object-store prefixes.                          | Partial; no topic ontology.                              |
| K - Knowledge  | No native representation of internalized expertise.                                                   | Poor. Requires external classifier and user-state model. |
| L - Legacy     | Could map archived folders or old buckets.                                                            | Partial; no lifecycle/archive semantics.                 |
| E - Essentials | No native identity-layer model.                                                                       | Poor. Requires external schema and governance.           |

## Source Semantics Preservation

| Requirement           | Mirage behavior                                                                                                                                                                                                                                                                                                                                                                                                                 | Fit                                            |
| --------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------- |
| Source identity       | Preserved through mount prefix and resource type. Index entries store `resource_type` and backend-specific `extra` (`research/mirage/python/mirage/cache/index/config.py:32`-`research/mirage/python/mirage/cache/index/config.py:40`).                                                                                                                                                                                         | Good at coarse source identity.                |
| Metadata              | `FileStat` includes name, size, modified, fingerprint, type, and `extra` (`research/mirage/python/mirage/types.py:39`-`research/mirage/python/mirage/types.py:47`).                                                                                                                                                                                                                                                             | Partial; backend-specific and not normalized.  |
| Permissions           | Mount mode is `read`, `write`, or `exec` (`research/mirage/python/mirage/types.py:50`-`research/mirage/python/mirage/types.py:53`). FUSE reports host user/group and generic file modes (`research/mirage/python/mirage/fuse/fs.py:70`-`research/mirage/python/mirage/fuse/fs.py:92`).                                                                                                                                          | Poor for source ACLs and per-user permissions. |
| Ownership             | No cross-source owner model in core `FileStat` or `IndexEntry`.                                                                                                                                                                                                                                                                                                                                                                 | Poor.                                          |
| Deduplication         | Cache can avoid repeated reads, but no global content identity or duplicate-resolution model is present in index/cache schemas.                                                                                                                                                                                                                                                                                                 | Poor.                                          |
| Sync/update semantics | Remote cache supports lazy/always freshness checks when a backend provides fingerprints (`research/mirage/python/mirage/workspace/workspace.py:374`-`research/mirage/python/mirage/workspace/workspace.py:402`). Backends that return no fingerprint silently fall back toward lazy behavior (`research/mirage/python/mirage/workspace/mount/registry.py:271`-`research/mirage/python/mirage/workspace/mount/registry.py:289`). | Partial.                                       |
| Conflict state        | VFP schema names `Conflict` as an error code (`research/mirage/python/mirage/vfp/schema/vfp-0.1.json:28`-`research/mirage/python/mirage/vfp/schema/vfp-0.1.json:36`), but no cross-source conflict-resolution state was found in core index/cache models.                                                                                                                                                                       | Poor.                                          |

## Multimodal Semantic Indexing Fit

Mirage recognizes several file types, but the architecture reduces most non-text content to bytes, metadata, or text conversions. Core file types include text, JSON, CSV, PNG/JPEG/GIF, ZIP/GZIP, PDF, Parquet, ORC, Feather, and HDF5 (`research/mirage/python/mirage/types.py:21`-`research/mirage/python/mirage/types.py:37`). The extension/mimetype detector maps the same families by file suffix or MIME type (`research/mirage/python/mirage/utils/filetype.py:17`-`research/mirage/python/mirage/utils/filetype.py:88`).

| Modality           | Native multimodal representation?                 | Mirage handling                                                                                                                                                                                                                                                                                                                                                                                 | Fit                                               |
| ------------------ | ------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------- |
| Text               | No semantic embeddings; shell/text commands only. | `cat`, `grep`, `rg`, `jq`, and resource-specific commands operate on text-like byte streams.                                                                                                                                                                                                                                                                                                    | Useful ingestion surface, not semantic retrieval. |
| Image              | No.                                               | Image MIME types exist in `FileType`, but no image embedding, OCR, captioning, or visual retrieval path is exposed in the reviewed core filetype code.                                                                                                                                                                                                                                          | Poor.                                             |
| Audio              | No.                                               | Optional audio commands require `sherpa-onnx` and a Whisper model; they transcribe WAV/MP3/OGG to text for `cat`, `grep`, `head`, `tail`, and `stat` (`research/mirage/docs/python/resource/s3.mdx:226`-`research/mirage/docs/python/resource/s3.mdx:248`; `research/mirage/python/mirage/commands/local_audio/utils.py:31`-`research/mirage/python/mirage/commands/local_audio/utils.py:142`). | Text fallback only.                               |
| Video              | No.                                               | No core `FileType` for video and no video extraction path in reviewed modality code.                                                                                                                                                                                                                                                                                                            | Unsupported.                                      |
| PDF                | No.                                               | PDF helper can render pages to PNG and extract text with pypdfium2 (`research/mirage/python/mirage/core/filetype/pdf.py:23`-`research/mirage/python/mirage/core/filetype/pdf.py:73`).                                                                                                                                                                                                           | Text/render fallback, not semantic.               |
| Structured/tabular | No embeddings.                                    | Docs describe Parquet/Feather/ORC/HDF5 command variants converting data to tabular text for shell processing (`research/mirage/docs/python/resource/s3.mdx:212`-`research/mirage/docs/python/resource/s3.mdx:224`).                                                                                                                                                                             | Useful for extraction, not semantic.              |

## Embedding And Model Strategy

No embedding/model strategy exists for indexing. The index schema stores listing metadata and `extra`, not vectors, model IDs, chunk IDs, embedding dimensions, or retrieval scores (`research/mirage/python/mirage/cache/index/config.py:32`-`research/mirage/python/mirage/cache/index/config.py:40`). Python dependencies include optional OpenAI and agent SDK extras (`research/mirage/python/pyproject.toml:108`-`research/mirage/python/pyproject.toml:152`), but those are integration surfaces, not a semantic index layer. Audio transcription is model-backed but uses a local sherpa-onnx Whisper recognizer and returns text chunks (`research/mirage/python/mirage/commands/local_audio/utils.py:43`-`research/mirage/python/mirage/commands/local_audio/utils.py:142`).

## Source Connectors Relevant To Us

Mirage has broad connector coverage for ingestion-like access:
- Local/infrastructure: RAM, Disk, OPFS, Redis, SSH (`research/mirage/docs/home/resource-matrix.mdx:15`-`research/mirage/docs/home/resource-matrix.mdx:25`).
- Object storage: S3, R2, GCS, OCI, Supabase (`research/mirage/docs/home/resource-matrix.mdx:27`-`research/mirage/docs/home/resource-matrix.mdx:35`).
- Google Workspace: Gmail, Drive, Docs, Sheets, Slides (`research/mirage/docs/home/resource-matrix.mdx:37`-`research/mirage/docs/home/resource-matrix.mdx:45`).
- Cloud files and SaaS: Dropbox, Box, GitHub, GitHub CI, Linear, Langfuse, Slack, Discord, Telegram, Email, MongoDB, Postgres, Notion, Trello, Paperclip, Semantic Scholar, PostHog, Vercel (`research/mirage/docs/home/resource-matrix.mdx:47`-`research/mirage/docs/home/resource-matrix.mdx:93`).

This connector breadth is Mirage's strongest applicability point. The issue is that connectors feed a shell/VFS interface, not an indexing engine.

## License

Mirage declares Apache-2.0 in Python package metadata (`research/mirage/python/pyproject.toml:1`-`research/mirage/python/pyproject.toml:8`) and includes the Apache License text (`research/mirage/LICENSE:1`-`research/mirage/LICENSE:3`). This is generally compatible with downstream commercial and open-source use, subject to normal notice/patent obligations.

## Maintainer Activity, Governance, And Bus Factor

The vendored Git metadata for the reviewed submodule shows one release tag (`v0.0.1`) and three commits through the pinned ref. Package metadata lists one author, Zecheng Zhang (`research/mirage/python/pyproject.toml:9`-`research/mirage/python/pyproject.toml:11`). `SECURITY.md` gives one email contact and GitHub private advisories as reporting paths (`research/mirage/SECURITY.md:12`-`research/mirage/SECURITY.md:20`) and states a target response/resolution timeline (`research/mirage/SECURITY.md:22`-`research/mirage/SECURITY.md:33`). Governance and bus-factor evidence is thin in the vendored repository.

## Concrete Adaptation Effort

Adopting Mirage for `indexit` would require a wrapper or fork; a plugin alone is unlikely to be sufficient.

Required work:
- Add an external Sparkle metadata layer that can label every indexed item S/P/A/R/K/L/E without encoding taxonomy in mount paths.
- Normalize source metadata, owner, ACL, and provenance across connectors.
- Add stable item IDs, content hashes, deduplication state, sync checkpoints, update detection, and conflict records.
- Add modality-specific extraction pipelines for text, image, audio, video, PDF, and tabular data.
- Add native embedding/model fan-out and a vector/full-text/hybrid retrieval backend.
- Harden daemon auth, snapshot load, request limits, SSH known-host defaults, logging redaction, and persistence encryption before any shared deployment.

Estimated effort: **high**. Mirage can reduce connector work, but the indexing, security, and semantic retrieval layers would still be mostly ours.

## Exit Cost

Exit cost is moderate if Mirage is used only as a source-access adapter because sources remain external and mount paths can be replaced by connector-specific ingestion code. Exit cost becomes high if downstream code adopts Mirage shell semantics, snapshots, mount path conventions, or VFP-like contracts as primary product APIs.

## Final Recommendation

**Reject** Mirage as the core `indexit` indexing/search solution.

Reasoning: Mirage is architecturally aligned with heterogeneous access, but our goals require durable cross-source semantic state and multimodal retrieval. Mirage provides neither native Sparkle modeling nor semantic/vector indexing. Its daemon security posture also needs hardening before it can be trusted in multi-user or service environments. Keep it on a watchlist as a connector/VFS substrate, especially if VFP matures into a stable protocol.
