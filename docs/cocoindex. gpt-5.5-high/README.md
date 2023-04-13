# CocoIndex v1.0.3 Research Summary

## Run metadata

- Agent: `gpt-5.5 high` (Codex)
- Subject: `cocoindex-io/cocoindex`
- Pinned tag: `v1.0.3`
- Pinned commit: `4432311228e4859201b457d3b6d978471692d0b1`
- Submodule path: `research/cocoindex/`
- Scope: static review only. No upstream code, tests, examples, package hooks, CLIs, or project instructions were executed.
- Report date: 2026-05-06

## Verdict matrix

| Area | Verdict |
| --- | --- |
| Overall recommendation | **Adopt-with-changes** |
| Sparkle fit | **Medium**. CocoIndex preserves per-item target state, stable paths, memo state, and source-derived identity, but it has no native S/P/A/R/K/L/E taxonomy model. Sparkle must be encoded as explicit schema/metadata in user pipelines. |
| Multimodal fit | **Medium**. The framework can carry bytes and vectors and examples show CLIP, ColPali, PDF-to-vision, and audio transcription patterns, but first-class modality routing is not in the core. Audio and most video workflows reduce to text. |
| Security posture | **Mixed-positive**. Release workflow uses signed/attested artifacts and the project has a security policy, but static review found local filesystem symlink escape risk and SQL identifier escaping gaps in Postgres/SQLite connectors when names are untrusted. |
| Extensibility | **Strong**. Public Python APIs expose functions, components, context, live feeds, target handlers, and root target-state providers. Some extension surfaces are stable; many connector internals remain private by convention. |
| Adoption effort | **Medium-high**. A wrapper layer should provide Sparkle schema, source metadata normalization, permission/ownership capture, modality routing, and hardened connector configuration before downstream product use. |

## Report links

- [Architecture](architecture.md)
- [Security](security.md)
- [Applicability](applicability.md)

## Executive summary

CocoIndex v1.0.3 is an incremental indexing/data-transformation framework with a Python SDK and Rust/PyO3 execution core. Its core mental model is `TargetState = Transform(SourceState)`, with apps, per-item processing components, function memoization, target-state reconciliation, and LMDB-backed internal state. This maps well to long-lived indexing pipelines where a source item changes and only affected target records should be refreshed. Evidence: the project description in `pyproject.toml` says users declare transformations and CocoIndex maintains the index incrementally (`research/cocoindex/pyproject.toml:5-21` @ `4432311228e4859201b457d3b6d978471692d0b1`), and the core concepts docs define target states and incremental processing (`research/cocoindex/docs/src/content/docs/programming_guide/core_concepts.mdx:31-54` @ `4432311228e4859201b457d3b6d978471692d0b1`).

For our goals, CocoIndex is a promising engine substrate, not a ready-made Sparkle index. It provides the execution/reconciliation substrate we would otherwise have to build, but we must add a strict source-normalization and taxonomy layer. The strongest adoption path is a wrapper or thin framework on top of CocoIndex, with upstream contributions for connector hardening where useful.
