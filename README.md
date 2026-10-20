# rework

[![CI](https://github.com/Dinosung/rework/actions/workflows/ci.yml/badge.svg)](https://github.com/Dinosung/rework/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)

**Write in Markdown. Deliver in your client's Word template, exactly.**

`pandoc --reference-doc` borrows a template's fonts, but not the rest of its house style: the
cover page is dropped, the header and footer come from the wrong section, the template's table
style is ignored, and pandoc points paragraphs at styles the template doesn't have. On 8 of 10
real company and university templates we tested, at least two of those broke.

`rework` reads the template, works out its house style, and fixes the pandoc output to match.

![The same Markdown report built with plain pandoc (left) and with rework (right) against one
house template. Left: no cover, no header or footer, the table collapses into lines, list numbers
lost. Right: the template's cover with the title, client and date filled in, its header and footer,
its table style and numbered list.](docs/before-after.png)

<sub>Both rendered with LibreOffice from the files in [`examples/`](examples). Word shows the plain
pandoc table less badly, but the cover, header, footer and styles are missing there too.</sub>

## Use it

Needs [pandoc](https://pandoc.org/installing.html) (tested with 3.1 and 3.12) and Python 3.10+.

```sh
pipx install git+https://github.com/Dinosung/REWORK
# or download the wheel from the latest release and: pipx install rework_docx-*.whl

rework build report.md -t client-template.docx -o report.docx
```

The package is `rework-docx`; the command is `rework`. Point `-t` at the client's template (.docx
or .dotx) or at any past deliverable that uses it. The template is only read, never changed.

Anything after `--` goes to pandoc. Often useful:

- `-- --toc` for a table of contents;
- `-- --number-sections` when the template's headings are numbered by typing rather than by style;
- `-- --shift-heading-level-by=1` when the template's sections use Heading 2;
- `-- --citeproc --bibliography refs.bib` for citations.

If the template numbers its captions ("Table 1", "Figure 1"), rework numbers yours the same way.

### Check what it learned

```sh
rework learn client-template.docx > style.json
```

```json
{
  "body": "ACME Body",
  "table": "Medium Shading 1 Accent 1",
  "table_cell": "ACME Table Text",
  "list": "List Paragraph",
  "caption": "Caption",
  "body_section": 1,
  "cover": 11,
  "cover_lines": ["ACME ENGINEERING", "[Report title]", "Prepared for [Client]", "[Date]"],
  "header_lines": ["[Client] | Confidential"],
  "replace": []
}
```

Edit anything it got wrong; styles can be given by name or id. Then fill the placeholders shown in
`cover_lines` and `header_lines` with `replace` pairs: the exact text to find, and what to put
there. Values in `{braces}` come from the Markdown's front matter (any plain-text field, such as
`title`, `date` or your own `client:`) or from `--set`:

```json
"replace": [["[Report title]", "{title}"], ["[Client]", "{client}"], ["[Date]", "{date}"]]
```

```sh
rework build report.md -t client-template.docx -s style.json --set client="Springfield County" -o report.docx
```

- The text is matched exactly, not as a pattern, and each placeholder keeps its formatting.
- A cover line replaced by `""` is removed, which is how to drop a template's instructions.
- A filled-in email address also updates its mailto link.
- The build stops if a `{value}` is missing and warns about text it didn't find.

Set `"cover": 0` if the template has no cover page. `learn` only copies short covers on its own;
for a longer one it adds a `cover_note` with the number to use. `"figure_caption"` and
`"table_caption"` override `"caption"` when the template has one style for each.

## With a coding agent

[`skill/SKILL.md`](skill/SKILL.md) is an agent skill: it tells Claude Code, Codex and similar agents
how to run `rework`, check what it learned and fill the cover fields from the template. Copy the
folder into your agent's skills directory.

## What it fixes

| | pandoc `--reference-doc` | rework |
|---|---|---|
| Body, table-cell, list and caption styles | pandoc's own names, often undefined in the template | the template's styles |
| Table style | a style called "Table" | the style the template's own tables use |
| Cover page | dropped | copied from the template, fields filled |
| Header, footer, page setup | from the template's first section (often the cover) | from the template's main section |
| Styles the template lacks | left undefined | matched by name, else pandoc's definition added |

## Limits

- House rules applied as direct formatting rather than styles (a hand-set indent, shading added
  cell by cell) are not copied.
- Headings numbered by typing the number, or by numbering set on single paragraphs, are not
  reproduced.
- List bullets and numbers use pandoc's numbering, not the template's own bullet characters and colours.
- One header per document body: templates that give each chapter its own section and typed header
  get the first chapter's header throughout.
- Caption numbers are plain ("Table 1"), not per chapter ("Table 3-1").
- `learn` guesses; check its output on a new template, especially `cover`.
- Tracked changes and comments are out of scope; see [pandoc's `--track-changes`](https://pandoc.org/MANUAL.html#option--track-changes).

## Contributing

A template `rework` gets wrong is the most useful report: see [CONTRIBUTING.md](CONTRIBUTING.md).
Changes are listed in the [changelog](CHANGELOG.md).

## License

[MIT](LICENSE)
