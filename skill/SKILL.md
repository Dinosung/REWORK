---
name: rework
description: Build a Word (.docx) deliverable from Markdown in a client's exact house style, using their template or a past deliverable. Use when asked to produce a report, proposal or document "in our template", "in the client's format" or as a branded .docx.
---

# Deliver Markdown in a client's Word template

Requires `rework` (`pipx install git+https://github.com/Dinosung/rework`) and pandoc.

1. Get the template: the client's .docx template or a past deliverable that uses it. Never edit it.
2. Learn its house style and look at it:
   ```sh
   rework learn TEMPLATE.docx > style.json
   ```
   Check `cover` and `cover_lines`. If the lines are not a cover page (for example a statement or
   a table of contents), set `"cover": 0`. If `cover_note` says a long cover was left out and the
   lines are a real cover, set `cover` to the number it gives.
3. If there is a cover, fill its blanks. For each placeholder line in `cover_lines` (such as
   "[Report title]", "Client name", a sample date), add a `replace` pair: a regular expression that
   matches the placeholder and a replacement using `{title}`, `{subtitle}`, `{author}`, `{date}`
   (from the Markdown front matter) or your own `{name}` supplied with `--set name=value`.
   Delete `cover_lines` when done (it is only informational).
4. Build:
   ```sh
   rework build REPORT.md -t TEMPLATE.docx -s style.json [--set client="..."] -o REPORT.docx
   ```
   If it warns that styles are still undefined, tell the user which ones.
5. Tell the user what to check by eye: the cover fields, the header and footer, and one table.
   rework does not copy formatting the template applies by hand rather than through styles.
