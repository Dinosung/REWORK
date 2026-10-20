# Changelog

All notable changes are listed here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and versions follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

Found by the first round of customer testing on nine templates the tool had never seen.

### Changed

- `replace` pairs match exact text, not regular expressions. Placeholders such as `[Client Name]`
  used to be read as patterns and garble the cover. Remove any `\\` escaping from existing pairs.
- `learn` reports style names ("Body Text") rather than ids ("af1"), and prints non-English text
  as is. style.json accepts either.

### Added

- Placeholders in headers and footers are filled too; `learn` lists them as `header_lines`.
- `{values}` come from any plain-text front-matter field, not only title, subtitle, author and date.
- A cover line replaced by `""` is removed, so template instructions can be dropped.
- `figure_caption` and `table_caption` keys; `learn` fills them from the template's Table Caption and
  Image Caption styles.
- Captions are numbered as Word fields ("Table 1") when the template numbers its own (`number_captions`).
- Headings marked `{.unnumbered}` stay out of the template's heading numbering.
- `cover_choices` lists where a long front matter can be cut.

### Fixed

- `learn` picks the body section by its chapter headings, and the body and list styles from that
  section, so a thesis template's abstract or contents section no longer wins.
- Images are found next to the source when rework runs from another folder.
- `-o` must name a .docx file.
- The abstract is no longer deleted along with pandoc's title block.
- Filling a placeholder keeps its formatting (underline, italics) and the rest of the paragraph.
- A value is never re-matched by another pair.
- A filled-in email address updates its mailto link.
- The build stops with a clear message when a `{value}` is missing or a `replace` entry is malformed,
  and warns about text it did not find. Bad paths and `--set` arguments give an error, not a traceback.
- Headers are listed before footers in the body section, which LibreOffice needs to keep the cover's
  own header and footer.
- pandoc's unused headers and footers are removed from the output.

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
