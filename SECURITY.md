# Security policy

`rework` opens .docx files, which are zip archives of XML, and runs pandoc on your Markdown. If you
find a way for a crafted template or Markdown file to read or write files outside the output,
run code, or exhaust memory, please report it privately.

## Reporting

Use [GitHub's private vulnerability reporting](https://github.com/Dinosung/rework/security/advisories/new).
Please don't open a public issue. You'll get a reply within a week.

## Supported versions

Only the latest release gets fixes.

Problems in pandoc itself belong in [pandoc's tracker](https://github.com/jgm/pandoc/security).
