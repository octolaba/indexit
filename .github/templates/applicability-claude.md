<!--
Applicability report template (Claude).

Copy this file to `docs/{{project_slug}}. {{agent_slug}}/applicability.md`
and replace every `{{placeholder}}` below. Remove this comment block once
the report is filled in.

Placeholders:
  {{project_slug}}     lowercase kebab-case repo name; matches
                       `research/<slug>/` (e.g. `cocoindex`, `mirage`, `qmd`)
  {{project_name}}     display name (e.g. `CocoIndex`); preserve upstream
                       capitalization
  {{version}}          pinned release tag (`vX.Y.Z`) or 12-char short SHA if
                       upstream publishes no tags
  {{agent_slug}}       lowercase normalized `{model}-{effort}`
                       (e.g. `claude-opus-4.7-xhigh`)
  {{commit}}           full 40-char commit SHA at the pin
  {{owner}}/{{repo}}   GitHub owner/repo segments

Scope: §3.3 + §4.3 of AGENTS.md / CLAUDE.md. Judge against indexit's two
goals (Sparkle consistency and multimodal semantic indexing), nothing more.
Every claim must cite `research/{{project_slug}}/<path>:<line>` at commit
`{{commit}}` (or a path inside `{{version}}`). When a §4.3 question does
not apply, state *why* it does not apply rather than skipping it.

Formatting rules (AGENTS.md / CLAUDE.md §6):
  - No `---` section separators — headings are enough.
  - Align table columns to width.
  - No blank line between a paragraph and its inline bullet list; only
    between a heading and the list that follows it.

Drop any section heading whose payload is genuinely empty or N/A — but
explain *why* in one sentence under the next heading, so the comparison
matrix across agents stays complete.
-->
# {{project_name}} {{version}} — Applicability for indexit

| Field         | Value                                                                                    |
| ------------- | ---------------------------------------------------------------------------------------- |
| Subject       | [{{owner}}/{{repo}}](https://github.com/{{owner}}/{{repo}}) @ `{{version}}`              |
| Pinned commit | `{{commit}}`                                                                             |
| Vendored at   | `research/{{project_slug}}/`                                                             |
| Analyst       | `{{agent_slug}}`                                                                         |
| Scope         | §3.3 + §4.3 — fit against Sparkle consistency (Goal 1) and multimodal indexing (Goal 2). |

## 1. Verdict

**Recommendation: {{adopt | adopt-with-changes | monitor | reject}}.**
One paragraph stating the decision and the single sharpest reason behind
it. If the verdict is conditional (e.g. *adopt-with-changes only for a
narrow K-bucket sub-product*), state the condition here and forward to the
adaptation section for the price tag.

| Dimension                    | Score | One-line summary                                  |
| ---------------------------- | ----- | ------------------------------------------------- |
| Sparkle fit                  |       |                                                   |
| Multimodal fit               |       |                                                   |
| Source-identity preservation |       |                                                   |
| Sync / update semantics      |       |                                                   |
| Security posture             |       | (carry over from `security.md`; do not re-derive) |
| Extensibility                |       |                                                   |
| Adoption effort              |       |                                                   |
| Exit cost                    |       |                                                   |

Scoring: **A** ready for our use · **B** usable, minor friction ·
**C** usable with non-trivial work · **D** blocking gap · **F** incompatible.

## 2. Sparkle (S/P/A/R/K/L/E) mapping

One paragraph stating what taxonomy primitives the project exposes
natively (collections, tags, paths, target schemas, mount prefixes, …)
and which Sparkle distinctions therefore have to live in our wrapper.

| Bucket             | Fit | Mapping (with citations) | Loss / adoption work |
| ------------------ | --- | ------------------------ | -------------------- |
| **S — Stream**     |     |                          |                      |
| **P — Projects**   |     |                          |                      |
| **A — Areas**      |     |                          |                      |
| **R — Resources**  |     |                          |                      |
| **K — Knowledge**  |     |                          |                      |
| **L — Legacy**     |     |                          |                      |
| **E — Essentials** |     |                          |                      |

Fit values: Strong · Medium · Marginal · Poor · None. Call out explicitly
which buckets *bend* (work with friction) and which *collapse* (cannot be
expressed at all) under the project's data model.

## 3. Source identity, metadata, permissions, dedup, sync, conflicts

| Attribute                    | Preserved? | Where (file:line @ commit) / what is lost |
| ---------------------------- | ---------- | ----------------------------------------- |
| Source identity (per item)   |            |                                           |
| Source identity (per system) |            |                                           |
| Path / key                   |            |                                           |
| MIME / file type             |            |                                           |
| Content hash                 |            |                                           |
| Title / display name         |            |                                           |
| Timestamps (created/mtime)   |            |                                           |
| Owner / principal            |            |                                           |
| Permissions / ACLs           |            |                                           |
| External system ID           |            |                                           |
| Cross-source deduplication   |            |                                           |
| Sync / update semantics      |            |                                           |
| Deletion propagation         |            |                                           |
| Conflict state               |            |                                           |

If a built-in connector preserves *different* attribute sets per source
(common for engines with many connectors), add a per-connector matrix
underneath this table — one row per connector, columns for the same
attributes — instead of bloating the schema-level table.

## 4. Multimodal handling

| Modality                          | Native multimodal? | Project handling (with citations) | Fallback path |
| --------------------------------- | ------------------ | --------------------------------- | ------------- |
| Text / markdown                   |                    |                                   |               |
| Source code                       |                    |                                   |               |
| Structured (CSV/Parquet/SQL rows) |                    |                                   |               |
| HTML                              |                    |                                   |               |
| PDF                               |                    |                                   |               |
| Image                             |                    |                                   |               |
| Audio                             |                    |                                   |               |
| Video                             |                    |                                   |               |

Native multimodal = embeddings/retrieval that operate on the raw modality
(CLIP, ColPali, native audio embedder). Fallback = OCR / ASR /
transcription / captioning / thumbnailing that reduces the modality to
text before indexing. One paragraph after the table on the *gap to indexit
Goal 2*: what we still have to build if we adopt.

## 5. Embedding strategy and pluggability

- Default models (with file:line @ commit).
- Text vs. per-modality embedder coverage; multi-vector (ColBERT/ColPali)
  support, if any.
- Pluggability surface: env vars, config keys, registry, plug-in API —
  cite the seam.
- Remote API integrations available out of the box (OpenAI, Cohere,
  Voyage, Bedrock, LiteLLM, …).
- Schema commitment: vector dimensionality, dtype, re-embedding cost on
  model swap.

## 6. Source connectors relevant to us

| Connector | Read | Write | Native identity preserved | Indexit relevance |
| --------- | ---- | ----- | ------------------------- | ----------------- |

List only connectors the project actually ships (with file path
evidence). After the table, name the connectors we'd need but the
project does **not** provide — they are the gap we must close or build
elsewhere.

## 7. License

One paragraph naming the license, citing the file (`LICENSE` or
`pyproject.toml`/`package.json`/`Cargo.toml` line), and stating
compatibility with downstream proprietary use. Flag any non-standard
clauses (commercial restrictions, attribution beyond Apache-2.0 norms,
SSPL/BSL, CLA requirements).

## 8. Maintainer activity, governance, bus factor

- License steward / backing org (foundation, company, BDFL).
- Release cadence (tags, dates) at the pinned snapshot — cite the
  changelog or git log.
- Contributor concentration: top-1 / top-3 commit share over a stated
  window; cite `security.md` if computed there.
- Governance artefacts present in the pinned tree (`GOVERNANCE.md`,
  `CONTRIBUTING.md`, `SECURITY.md`, code of conduct).
- Bus factor estimate and what it implies for our adoption window.

## 9. Adaptation effort

State 1–3 plausible adoption shapes (wrapper / fork / upstream
contribution / replacement) and cost each one. Pick the shape this
report recommends and explain why the others are worse.

| Work item | Mode (wrapper/fork/upstream/user code) | Estimate |
| --------- | -------------------------------------- | -------- |

Total floor / ceiling line under the table, in dev-weeks or dev-months,
calibrated to one engineer familiar with the stack. If the recommendation
is conditional (§1), give one estimate per condition (e.g. *narrow
sub-product* vs. *indexit core*).

## 10. Exit cost

One paragraph. Cover: license escape, data portability (what stays in
external stores we own vs. what is locked in the project's internal
state), pipeline rewrite cost if we eject. Conclude with a single label:
**Low / Medium / High**, and the conditions under which it changes
(e.g. *Low while used as SDK; High if we adopt its daemon as a product
API*).

## 11. Final recommendation

> **{{adopt | adopt-with-changes | monitor | reject}}.**
>
> Restate the verdict, then list the conditions / changes required to
> earn it. For *adopt-with-changes*, list the concrete patches and which
> mode delivers them (wrapper / upstream PR / fork). For *monitor*, list
> the re-evaluation triggers (e.g. *daemon auth lands in a tagged
> release*, *a second maintainer joins*). For *reject*, name the closest
> alternative or the gap that would have to close for re-evaluation.

## 12. §4.3 mandatory checklist

| Question                                                                     | Answer (§ reference) |
| ---------------------------------------------------------------------------- | -------------------- |
| Map onto Sparkle (S/P/A/R/K/L/E); which buckets bend/collapse                | §2                   |
| Non-text modalities: first-class or text-conversion fallback                 | §4                   |
| Source identity / metadata / permissions / dedup / sync / conflict preserved | §3                   |
| Modalities with native multimodal vs. text fallbacks                         | §4                   |
| Embedding/model strategy and pluggability                                    | §5                   |
| Source connectors relevant to us                                             | §6                   |
| License compatibility                                                        | §7                   |
| Maintainer activity / governance / bus factor                                | §8                   |
| Adaptation effort (fork / plugin / wrapper / contribution)                   | §9                   |
| Exit cost                                                                    | §10                  |
| Final recommendation with reasoning                                          | §11                  |

Replace each "§N" with the actual answer (one sentence, plus a section
pointer for depth). The checklist is the cross-agent comparison surface —
do not omit rows, even when the answer is "not applicable, because …".
