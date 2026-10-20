# rework

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

Needs [pandoc](https://pandoc.org/installing.html) and Python 3.10+.

```sh
pipx install git+https://github.com/Dinosung/rework     # or: pip install ...

rework build report.md -t client-template.docx -o report.docx
```

Point `-t` at the client's template or at any past deliverable that uses it. The template is only
read, never changed. Anything after `--` is passed to pandoc (for example `-- --toc`).

### Check what it learned

```sh
rework learn client-template.docx > style.json
```

```json
{
  "body": "ACMEBody",
  "table": "MediumShading1-Accent1",
  "table_cell": "ACMETableText",
  "list": "ListParagraph",
  "caption": "Caption",
  "body_section": 1,
  "cover": 11,
  "cover_lines": ["ACME ENGINEERING", "[Report title]", "Prepared for [Client]", "[Date]"],
  "replace": []
}
```

Edit anything it got wrong, then fill the cover's blanks with `replace` pairs (a regular
expression and its replacement). `{title}`, `{subtitle}`, `{author}` and `{date}` come from the
Markdown's front matter; anything else comes from `--set`:

```json
"replace": [["\\[Report title\\]", "{title}"], ["\\[Client\\]", "{client}"], ["\\[Date\\]", "{date}"]]
```

```sh
rework build report.md -t client-template.docx -s style.json --set client="Springfield County" -o report.docx
```

Set `"cover": 0` if the template has no cover page. `learn` only copies short covers on its own;
for a longer one it adds a `cover_note` with the number to use.

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
- `learn` guesses; check its output on a new template, especially `cover`.
- Tracked changes and comments are out of scope; see [pandoc's `--track-changes`](https://pandoc.org/MANUAL.html#option--track-changes).

## License

MIT
