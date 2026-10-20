# Changelog

All notable changes are listed here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and versions follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.1.0] - 2026-10-20

First release.

### Added

- `rework build`: runs pandoc with the template as `--reference-doc`, then applies the template's
  body, table, table-cell, list and caption styles, its cover page with fields filled, and the header,
  footer and page setup of its main section.
- `rework learn`: works out a template's house style and prints it as JSON to check or edit.
- Cover detection that stops at a page or section break or a table of contents, and only suggests
  long front matter (`cover_note`).
- Styles pandoc uses but the template lacks are matched by name, or pandoc's definition is added.
- Content types are registered for parts pandoc leaves without one (embedded fonts), so Word opens
  the result.
- An agent skill (`skill/SKILL.md`) for Claude Code, Codex and similar agents.

[Unreleased]: https://github.com/Dinosung/REWORK/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/Dinosung/REWORK/releases/tag/v0.1.0
