# Changelog

All notable changes are listed here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and versions follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.3.0] - 2026-10-21

Found by the second round of customer testing on six more templates the tool had never seen.

### Added

- `cover_choices` runs to where the body starts and marks page and section breaks; `cover_note`
  says when front matter continues past the cover.
- `quote` key: block quotes use the template's Quote style. Captions use the template's own caption
  styles, such as "Table or chart caption".
- `heading_note` when the template's sections start below Heading 1.
- `--strict` fails the build when there are warnings.

### Fixed

- The README example still used regular-expression escapes and left its cover unfilled.
- The body always starts on a new page after the cover.
- A table of contents heading no longer takes chapter number 1.
- A template whose base style is white (for a dark cover) no longer gives invisible body text.
- A style name wins over another style's id ("TableNormal").
- A link whose text a replacement covered is removed with a warning, and unchanged links no longer warn.
- Table captions keep with their table; a past deliverable's page numbering restarts at 1.
- Text boxes are read once in `cover_lines`; page numbers are left out of `header_lines`.
- The table style comes from data tables, not layout tables.
- `learn` explains a missing or non-Word file; `-o` in a missing folder is reported as such.
- A warning says when unfilled text lies outside the copied cover.

## [0.2.0] - 2026-10-20

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

[Unreleased]: https://github.com/Dinosung/REWORK/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/Dinosung/REWORK/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/Dinosung/REWORK/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/Dinosung/REWORK/releases/tag/v0.1.0
