<!--
Applicability report template (GPT).

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
                       (e.g. `gpt-5.5-xhigh`)
  {{commit}}           full 40-char commit SHA at the pin
  {{owner}}/{{repo}}   GitHub owner/repo segments

Scope: AGENTS.md / CLAUDE.md sections 3.3 and 4.3. Judge against indexit's
two goals: Sparkle consistency and multimodal semantic indexing. Every claim
about upstream behavior must cite `research/{{project_slug}}/<path>:<line>`
at commit `{{commit}}`. When a section 4.3 question does not apply, state
why rather than skipping it.

No-loss migration check:
  - Bucket-level Sparkle evidence belongs in section 2.
  - Source identity, metadata, ACL, dedup, sync, deletion, and conflict
    evidence belongs in section 3.
  - Modality, extraction, embedding, retrieval, and fallback evidence belongs
    in section 4.
  - Model, connector, license, governance, bus-factor, security carry-over,
    operational blocker, adoption recipe, re-evaluation trigger, and exit-cost
    evidence belongs in sections 5-8.
  - If useful evidence does not fit, add one row to section 7 rather than
    dropping it.

Formatting rules:
  - No `---` section separators; headings are enough.
  - Align table columns to width.
  - Do not put a blank line between a paragraph and its inline bullet list;
    only separate lists from headings.
-->
# {{project_name}} {{version}} - Applicability for indexit

| Field         | Value                                                                               |
| ------------- | ----------------------------------------------------------------------------------- |
| Subject       | [{{owner}}/{{repo}}](https://github.com/{{owner}}/{{repo}}) @ `{{version}}`         |
| Pinned commit | `{{commit}}`                                                                        |
| Vendored at   | `research/{{project_slug}}/`                                                        |
| Analyst       | `{{agent_slug}}`                                                                    |
| Scope         | Fit against Sparkle consistency (Goal 1) and multimodal semantic indexing (Goal 2). |

## 1. Verdict

**Recommendation: {{adopt | adopt-with-changes | monitor | reject}}.**
State the decision in one paragraph: what role this project should or should
not play for indexit, the decisive reason, and the main condition if the
verdict is conditional.

| Dimension                  | Grade | One-line implication for indexit                      |
| -------------------------- | ----- | ----------------------------------------------------- |
| Sparkle fit                |       |                                                       |
| Multimodal fit             |       |                                                       |
| Source semantics           |       |                                                       |
| Model / embedding strategy |       |                                                       |
| Connector coverage         |       |                                                       |
| Extensibility              |       | Stable public surfaces vs. private/internal seams.    |
| License / project health   |       |                                                       |
| Security carry-over        |       | Carry over from `security.md`; do not re-run it here. |
| Adoption effort            |       |                                                       |
| Exit cost                  |       |                                                       |

Grades: **A** ready for indexit; **B** usable with minor friction; **C** usable
with meaningful work; **D** blocking gap; **F** incompatible.

## 2. Sparkle mapping

Explain in one paragraph which native primitives could carry taxonomy state
(collections, paths, tags, schemas, mounts, resources, rows, metadata fields)
and which Sparkle distinctions would have to live in an indexit wrapper.

| Bucket             | Fit | Native mapping / evidence | What bends, collapses, or must be added |
| ------------------ | --- | ------------------------- | --------------------------------------- |
| **S - Stream**     |     |                           |                                         |
| **P - Projects**   |     |                           |                                         |
| **A - Areas**      |     |                           |                                         |
| **R - Resources**  |     |                           |                                         |
| **K - Knowledge**  |     |                           |                                         |
| **L - Legacy**     |     |                           |                                         |
| **E - Essentials** |     |                           |                                         |

Fit values: Strong, Medium, Marginal, Poor, None. End with one sentence naming
the buckets that bend and the buckets that collapse under the project model.

## 3. Source semantics preservation

Use this table for the schema-level answer. If preservation varies materially
by connector, add a short connector-specific table after it.

| Attribute                  | Preserved? | Evidence and indexit implication |
| -------------------------- | ---------- | -------------------------------- |
| Source identity per item   |            |                                  |
| Source identity per system |            |                                  |
| Path / key                 |            |                                  |
| External system ID         |            |                                  |
| MIME / file type           |            |                                  |
| Title / display name       |            |                                  |
| Content hash / fingerprint |            |                                  |
| Created / modified time    |            |                                  |
| Owner / principal          |            |                                  |
| Permissions / ACLs         |            |                                  |
| Cross-source deduplication |            |                                  |
| Sync / update semantics    |            |                                  |
| Deletion propagation       |            |                                  |
| Conflict state             |            |                                  |

| Connector or source class | Identity preserved | Metadata preserved | ACL preserved | Sync / conflict implication |
| ------------------------- | ------------------ | ------------------ | ------------- | --------------------------- |
|                           |                    |                    |               |                             |

## 4. Multimodal handling

Summarize whether the project has modality-specific extraction, embedding,
indexing, and retrieval, or merely accepts preconverted text.

| Modality              | Project handling / evidence | Native multimodal? | Fallback path and indexit gap |
| --------------------- | --------------------------- | ------------------ | ----------------------------- |
| Text / markdown       |                             |                    |                               |
| Source code           |                             |                    |                               |
| Structured / tabular  |                             |                    |                               |
| HTML / web content    |                             |                    |                               |
| PDF / document images |                             |                    |                               |
| Image                 |                             |                    |                               |
| Audio                 |                             |                    |                               |
| Video                 |                             |                    |                               |

Native multimodal means embeddings or retrieval operate on the raw modality
or modality-native representation (for example CLIP, ColPali, native audio
embeddings). OCR, ASR, transcripts, captions, thumbnails, and summaries are
text-conversion fallbacks. End with the remaining gap to indexit Goal 2.

## 5. Models and connectors

| Topic                             | Answer with citations |
| --------------------------------- | --------------------- |
| Default embedding / model stack   |                       |
| Per-modality model coverage       |                       |
| Pluggability surface              |                       |
| Extension points / API stability  |                       |
| Remote API integrations           |                       |
| Vector schema / re-embedding cost |                       |
| Retrieval strategy                |                       |

| Connector or target | Read | Write | Native identity preserved | Indexit relevance |
| ------------------- | ---- | ----- | ------------------------- | ----------------- |
|                     |      |       |                           |                   |

After the connector table, list the relevant connectors indexit needs but the
project does not ship.

## 6. License and project health

| Area                         | Assessment with citations |
| ---------------------------- | ------------------------- |
| License compatibility        |                           |
| Backing org / governance     |                           |
| Release cadence              |                           |
| Maintainer activity          |                           |
| Bus factor                   |                           |
| Security carry-over          |                           |
| Dependency / model ownership |                           |

Keep security here to adoption impact only. Detailed vulnerabilities belong in
`security.md`; this row should say what they change about the recommendation.

## 7. Adoption path

| Adoption shape        | When viable | Effort | Recommendation impact |
| --------------------- | ----------- | ------ | --------------------- |
| Direct adoption       |             |        |                       |
| Wrapper / consumer    |             |        |                       |
| Plugin / extension    |             |        |                       |
| Upstream contribution |             |        |                       |
| Fork                  |             |        |                       |
| Replacement           |             |        |                       |

| Work item | Mode | Estimate |
| --------- | ---- | -------- |
|           |      |          |

Total floor / ceiling: `{{estimate}}` for one engineer familiar with the stack.

| Adoption-critical note | Impact | Evidence / target section |
| ---------------------- | ------ | ------------------------- |
|                        |        |                           |

Use the final table only for useful evidence that would otherwise be lost:
operational red flags, strengths that change the verdict, monitor triggers,
or required deployment constraints.

## 8. Exit cost and final recommendation

Exit cost: **{{Low | Medium | High}}.** One paragraph covering license escape,
data portability, project-specific state, model/vector lock-in, and the rewrite
cost if indexit ejects.

> **{{adopt | adopt-with-changes | monitor | reject}}.**
>
> Restate the final decision and the exact conditions. For
> `adopt-with-changes`, name the required wrapper, fork, plugin, or upstream
> work. For `monitor`, list re-evaluation triggers. For `reject`, name the gap
> that would have to close before re-review.

## 9. Mandatory section 4.3 checklist

| Question                                                                     | Answer / section pointer |
| ---------------------------------------------------------------------------- | ------------------------ |
| Sparkle mapping and buckets that bend or collapse                            |                          |
| Non-text modalities as first-class support or text-conversion fallback       |                          |
| Source identity / metadata / permissions / dedup / sync / conflict preserved |                          |
| Modalities with native multimodal representations vs. text fallbacks         |                          |
| Embedding / model strategy and pluggability                                  |                          |
| Source connectors relevant to indexit                                        |                          |
| License compatibility                                                        |                          |
| Maintainer activity / governance / bus factor                                |                          |
| Adaptation effort: fork, plugin, wrapper, or upstream contribution           |                          |
| Exit cost                                                                    |                          |
| Final recommendation with reasoning                                          |                          |

Every row must contain a direct answer, not only a section number. Keep the
answer to one sentence when possible and use the section pointer for detail.
