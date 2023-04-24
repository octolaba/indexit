# Mirage Research Report

All citations refer to `research/mirage` at pinned upstream commit `8b99fb9247ecb40725d4718bac58e3bb230aad34` (`v0.0.1`).

## Run Metadata

| Field | Value |
| --- | --- |
| Project | Mirage |
| Upstream repository | `strukto-ai/mirage` |
| Reviewed ref | `v0.0.1` |
| Reviewed commit | `8b99fb9247ecb40725d4718bac58e3bb230aad34` |
| Agent | `gpt-5.5-xhigh` |
| Identity source | `/Users/kamilsk/.codex/sessions/2026/05/08/rollout-2026-05-08T09-24-49-019e0642-9e71-7c32-b310-e141a09c638d.jsonl` |
| Identity confidence | `high` |
| Review date | 2026-05-08 |
| Review method | Static inspection only; no Mirage code, tests, examples, build tools, or package managers were executed. |

## Executive Verdict

Mirage is a promising virtual filesystem and shell abstraction for AI agents, not a ready indexing or semantic retrieval engine. The project explicitly presents itself as "a Unified Virtual File System for AI Agents" that mounts services such as S3, Google Drive, Slack, Gmail, and Redis into one filesystem tree (`research/mirage/README.md:26`) and routes bash-like commands over mounted resources (`research/mirage/docs/home/architecture.mdx:16`-`research/mirage/docs/home/architecture.mdx:28`).

For `indexit`, Mirage should be **rejected as the core indexing/search engine**. It lacks native Sparkle taxonomy state, vector or semantic index storage, multimodal embeddings, source permission preservation, and conflict/deduplication semantics. It is worth monitoring as a connector/VFS substrate if we later want a shell-oriented ingestion layer.

## Comparison Matrix

| Dimension | Assessment | Evidence |
| --- | --- | --- |
| Recommendation | **Reject** for core indexing; monitor as connector substrate | Mirage's index cache stores directory/listing metadata (`id`, `name`, `resource_type`, timestamps, `size`, `extra`) rather than embeddings or semantic vectors (`research/mirage/python/mirage/cache/index/config.py:32`-`research/mirage/python/mirage/cache/index/config.py:40`). |
| Sparkle fit | Partial structural fit only | Mount prefixes preserve source/resource boundaries (`research/mirage/python/mirage/workspace/mount/registry.py:26`-`research/mirage/python/mirage/workspace/mount/registry.py:32`), but there is no taxonomy model beyond path/resource metadata. |
| Multimodal fit | Weak | Core file types cover text, structured data, image MIME types, PDF, and archives, but no audio/video enum (`research/mirage/python/mirage/types.py:21`-`research/mirage/python/mirage/types.py:37`); audio is an opt-in transcription layer, not native multimodal retrieval (`research/mirage/docs/python/resource/s3.mdx:226`-`research/mirage/docs/python/resource/s3.mdx:248`). |
| Security posture | Early alpha, not safe as a multi-user daemon | The daemon wires routers without authentication middleware (`research/mirage/python/mirage/server/app.py:116`-`research/mirage/python/mirage/server/app.py:129`) while the CLI only sends a bearer header client-side (`research/mirage/python/mirage/cli/client.py:48`-`research/mirage/python/mirage/cli/client.py:55`). |
| Extensibility | Good for VFS resources and commands | Resource registry, mount dispatch, command/op registration, and filetype-specific handlers are explicit extension surfaces (`research/mirage/python/mirage/resource/registry.py:28`-`research/mirage/python/mirage/resource/registry.py:137`; `research/mirage/python/mirage/workspace/mount/mount.py:29`-`research/mirage/python/mirage/workspace/mount/mount.py:40`). |
| Adoption effort | High for our goals | A production adoption would require an external Sparkle classifier, source ACL model, semantic/vector index, modality-specific model fan-out, sync/conflict tracking, and daemon hardening. |

## Report Files

- [architecture.md](architecture.md) - C4-style architecture, indexing-pipeline analysis, storage and runtime model.
- [security.md](security.md) - static security review, findings, trust boundaries, secrets, logging, and release posture.
- [applicability.md](applicability.md) - Sparkle and multimodal fit, connector coverage, adoption work, and final recommendation.

