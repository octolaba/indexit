> # 🗃️ indexit
> 
> It's all indexed.

The repository for researching open-source projects related to indexing data sources.

## Researches

### CocoIndex

[CocoIndex](https://cocoindex.io/) is the first researched project
in this repository. The analysis is pinned to `cocoindex-io/cocoindex` `v1.0.3`
(`4432311228e4859201b457d3b6d978471692d0b1`) and was performed independently
by two models:

- [GPT report](docs/cocoindex.%20gpt-5.5-high/README.md) — `gpt-5.5 high`
  static review covering architecture, security, and applicability.
- [Claude report](docs/cocoindex.%20claude-opus-4.7-high/README.md) —
  `claude-opus-4.7 high` static review covering the same research checklist.

### QMD

[QMD](https://github.com/tobi/qmd) is the second researched project. The
analysis is pinned to `tobi/qmd` `v2.1.0`
(`65cd1b3fd02891d1ee0eefa751620918664fa321`) and was performed independently
by two models at `xhigh` reasoning effort:

- [GPT report](docs/qmd.%20gpt-5.5-xhigh/README.md) — `gpt-5.5 xhigh`
  static review. Verdict: **reject** as the core downstream substrate;
  monitor as a design reference for local hybrid markdown retrieval.
- [Claude report](docs/qmd.%20claude-opus-4.7-xhigh/README.md) —
  `claude-opus-4.7 xhigh` static review. Verdict: **monitor**, with a narrow
  **adopt-with-changes** path if a Markdown-RAG sub-product is in scope.

### Mirage

[Mirage](https://github.com/strukto-ai/mirage) is the third researched project.
The analysis is pinned to `strukto-ai/mirage` `v0.0.1`
(`8b99fb9247ecb40725d4718bac58e3bb230aad34`) and was performed independently
by two models at `xhigh` reasoning effort:

- [GPT report](docs/mirage.%20gpt-5.5-xhigh/README.md) — `gpt-5.5 xhigh`
  static review. Verdict: **reject** as the core indexing/search engine;
  **monitor** as a connector/VFS substrate.
- [Claude report](docs/mirage.%20claude-opus-4.7-xhigh/README.md) —
  `claude-opus-4.7 xhigh` static review. Verdict: **monitor**, with an
  **adopt-with-changes** path as an embedded connector layer once daemon
  auth, snapshot-load hardening, and SSH host-key defaults land upstream.
