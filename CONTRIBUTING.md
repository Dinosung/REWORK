# Contributing

Thanks for helping. The most useful contribution is a template that `rework` gets wrong.

## Report a template it gets wrong

Open a [template issue](https://github.com/Dinosung/rework/issues/new?template=template.yml) with:

- the template, or a stripped copy (delete the text, keep the styles, cover and headers), if you can share it;
- the output of `rework learn TEMPLATE.docx`;
- what came out wrong (a screenshot helps).

Never attach a client's confidential document. A blank copy of the template is enough.

## Develop

Needs Python 3.10+ and [pandoc](https://pandoc.org/installing.html).

```sh
git clone https://github.com/Dinosung/rework && cd rework
python -m venv .venv && . .venv/bin/activate
pip install -e ".[test]" ruff
pytest -q
ruff check .
```

Tests build their templates with python-docx, so there are no binary fixtures to keep in sync.
For a fix to template handling, add a test that builds a small template showing the problem.

## Pull requests

- Keep each pull request to one change, with a test when behaviour changes.
- Keep the code small and plain; `rework` is a few hundred lines on purpose.
- CI runs ruff and the tests on Python 3.10 and 3.13 with the latest pandoc.

By contributing you agree that your work is released under the [MIT License](LICENSE).

## Releasing

Bump `version` in `pyproject.toml` and `rework/__init__.py`, move the changelog's Unreleased notes
under the new version, and push to main. The release workflow tags the commit and publishes a
GitHub release with the built packages.
