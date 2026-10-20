---
name: rework
description: Build a Word (.docx) deliverable from Markdown in a client's exact house style, using their template or a past deliverable. Use when asked to produce a report, proposal or document "in our template", "in the client's format" or as a branded .docx.
---

# Deliver Markdown in a client's Word template

Requires `rework` (`pipx install git+https://github.com/Dinosung/REWORK`, command `rework`) and
[pandoc](https://pandoc.org/installing.html).

1. Get the template: the client's .docx template or a past deliverable that uses it. Never edit it.
2. Learn its house style:
   ```sh
   rework learn TEMPLATE.docx > style.json
   ```
   Look at the template itself too, if you can render pages
   (`soffice --headless --convert-to pdf TEMPLATE.docx && pdftoppm -png -r 50 TEMPLATE.pdf page`).
   Check `cover` and `cover_lines`. If the lines are not a cover page (for example a statement or
   a table of contents), set `"cover": 0`. If `cover_note` says a long cover was left out and the
   lines are a real cover, set `cover` to the number it gives.
3. Fill the placeholders in `cover_lines` and `header_lines` with `replace` pairs: the exact text
   to find (copied as is, no escaping) and the replacement, for example
   ```json
   "replace": [["[Report title]", "{title}"], ["[Client Name]", "{client}"], ["Delete this note", ""]]
   ```
   - Map by meaning, not by name: a `<TITLE>` under "Prepared by" is a job title, not the report title.
   - `{name}` values come from the Markdown front matter (`title`, `date`, or any field such as
     `client:`) or from `--set name=value`.
   - Replacing a line with `""` removes it; use that for template instructions on the cover.
   - Remove `cover_lines` and `header_lines` from style.json when done; they are only informational.
4. Build:
   ```sh
   rework build REPORT.md -t TEMPLATE.docx -s style.json [--set client="..."] -o REPORT.docx
   ```
   Fix every `rework: warning:` (text not found, a link still pointing elsewhere, undefined
   styles) and rebuild. An `error` names the missing value or the bad entry.
5. Check the result, rendering it as in step 2 if you can, against the template: cover fields,
   header and footer, one table. Then tell the user:
   - which front-matter fields had no place in the template;
   - which template pages after the cover were not carried over (a legal notice, revision
     history or table of contents); raise `cover` to keep them, or pass `-- --toc` for a contents page;
   - that formatting the template applies by hand rather than through styles (table shading,
     spacing) is not copied.
