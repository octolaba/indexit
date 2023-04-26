# Mirage — Analysis (claude-opus-4.7, xhigh)

## Run metadata

| Field            | Value                                                     |
| ---------------- | --------------------------------------------------------- |
| Subject          | [strukto-ai/mirage](https://github.com/strukto-ai/mirage) |
| Pinned tag       | `v0.0.1`                                                  |
| Pinned commit    | `8b99fb9247ecb40725d4718bac58e3bb230aad34`                |
| Submodule        | `research/mirage/`                                        |
| Reviewing agent  | Claude Opus 4.7 (1M context)                              |
| Reasoning effort | xhigh                                                     |
| Agent slug       | `claude-opus-4.7-xhigh`                                   |
| Workflow         | `CLAUDE.md` / `AGENTS.md` §3–§5                           |

## Reports

* [`architecture.md`](architecture.md) — C4 (context, container,
  component) + indexing pipeline + extension surfaces + stack.
* [`security.md`](security.md) — code-level scan: 4 high-severity, 4
  medium, 5 low, 2 info. Each finding cites file + line at the pin.
* [`applicability.md`](applicability.md) — Sparkle (S/P/A/R/K/L/E)
  mapping, multimodal handling, license, governance, bus factor,
  adaptation effort, final verdict.

## What Mirage actually is (one paragraph)

Mirage is a **unified virtual filesystem (VFS) for AI agents**: a
single tree under which 22 heterogeneous backends (S3, GitHub, Slack,
GDrive, Notion, Postgres, SSH, …) get mounted as folders, and a
tree-sitter-bash-driven executor lets agents read, pipe, and search
across them with `ls`/`cat`/`grep`/`find`/`jq`/`cp`/`mv`. It ships a
Python library + CLI + FastAPI daemon (default `127.0.0.1:8765`) +
optional FUSE bridge, and a sibling TypeScript monorepo with the same
shape. **It is not an indexer.** Its "index cache" is a TTL'd
directory-listing/metadata cache, not a search index; there is no
embedding model, no vector store, no semantic search. For indexit's
purposes it is a *source-abstraction layer* a future indexer could sit
on top of, not the indexer itself.

## Verdict matrix

| Dimension            | Verdict                                        | Notes                                                                                                                                                                                                                                                                                                      |
| -------------------- | ---------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Sparkle fit**      | **Neutral**                                    | Cleanly serves Stream + Resources backends as mounts; does not classify, dedup, or surface upstream ACLs. The bucket distinctions S/P/A/R/K/L/E remain a problem for the indexer above Mirage                                                                                                              |
| **Multimodal fit**   | **Poor** (text/structured only)                | No native multimodal embeddings. Audio is handled via offline ASR (sherpa-onnx text fallback). Image / PDF are byte-level reads. Video unsupported                                                                                                                                                         |
| **Security posture** | **Alpha — exploitable in default daemon mode** | Daemon HTTP API is unauthenticated despite client-side token plumbing; `native=true` execute is raw `subprocess_shell`; `DiskResource.load_state` has a path-traversal in snapshot reload; SSH defaults to `known_hosts=None` (MITM). Runtime disk path-traversal is correctly defended. See `security.md` |
| **Extensibility**    | **Strong**                                     | Public surfaces: Resource registry, Command registry, Cache stores, Index stores, Observer resource, Agent SDK adapters. Backwards compatibility explicitly *not* committed at this stage                                                                                                                  |
| **Adoption effort**  | **Low–Medium as wrapper / consumer**           | 1–2 weeks for an MVP that uses `Workspace` as a connector library inside our indexer service. Higher if we adopt the daemon                                                                                                                                                                                |

## Final recommendation

**Monitor.** Mirage solves a different problem than indexit; adopting
it as our indexer would force us to build the indexer above it anyway.
Adopting it as a *connector layer* is technically feasible — the
breadth of backends is hard to replicate — but v0.0.1 is alpha-quality
with one critical, four high, and four medium security findings. Bus
factor is 1, with three commits in the public repo at the pin. Watch
for: daemon auth, snapshot-load hardening, SSH host-key default-on,
and a second maintainer. Re-evaluate at v0.1.x.

Adoption shape if we eventually flip to **adopt-with-changes**: embed
the `Workspace` SDK in our own service (skip the daemon entirely),
allowlist resources, wrap `execute` with a policy gate that strips
`native=True`, override SSH `known_hosts`, vendor Mirage as a git
submodule pinned to a tag. Detail in `applicability.md` §9.

## Acceptance-criteria self-check

* All claims cite a path inside `research/mirage/` at commit
  `8b99fb9247ecb40725d4718bac58e3bb230aad34` (or a `v0.0.1` file). ✔
* Every §4.1 / §4.2 / §4.3 question is answered explicitly:
  architecture, security, and applicability reports each include a
  question-by-question checklist. ✔
* Security review goes beyond CVE/OSV/Dependabot echo: `security.md`
  reports concrete code-level findings (paths + line numbers) plus
  explicit "reviewed, no issues found" entries for tar-extract
  traversal, runtime disk path-traversal, YAML loading, and
  pickle/exec of user data. ✔
* Applicability ends with one of the four verdicts and the reasoning:
  **monitor**, with explicit re-evaluation triggers. ✔
* Reports are written in English; folder name follows the §5 layout
  (`docs/mirage. claude-opus-4.7-xhigh/`). ✔

## Watch list / re-evaluation triggers

1. Server-side enforcement of `MIRAGE_AUTH_TOKEN` lands in a tagged
   release (`security.md` §3.1).
2. `DiskResource.load_state` validates manifest keys against
   `relative_to(self.root)` (`security.md` §3.4).
3. SSH connection defaults to using the user's
   `~/.ssh/known_hosts` instead of skipping verification
   (`security.md` §3.5).
4. Observable contribution cadence beyond the original maintainer
   (`applicability.md` §5).
5. A search-pushdown / embedder extension surface lands upstream
   (`applicability.md` §6, `architecture.md` §7).

## Provenance

Submodule pinned to `v0.0.1`:

```
$ git -C research/mirage describe --tags
v0.0.1
$ git -C research/mirage rev-parse HEAD
8b99fb9247ecb40725d4718bac58e3bb230aad34
$ git submodule status research/mirage
 8b99fb9247ecb40725d4718bac58e3bb230aad34 research/mirage (v0.0.1)
```

This dossier was produced by Claude Opus 4.7 (1M context) at reasoning
effort `xhigh` on 2026-05-08 against the static checkout above. No code
inside `research/mirage/` was executed during this review (per
`CLAUDE.md` §6).
