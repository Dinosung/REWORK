"""rework: put your Markdown into a client's Word template, in their exact house style."""
import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from . import __version__
from .apply import apply
from .learn import learn

# pandoc's Word output drops the {.unnumbered} class; mark those headings' text with a character
# style so rework can turn off the template's heading numbering on them.
UNNUMBERED_FILTER = """
function Header(h)
  if h.classes:includes("unnumbered") then
    h.content = {pandoc.Span(h.content, {["custom-style"] = "Rework Unnumbered"})}
  end
  return h
end
"""


def build(source: str, template: str, output: str, style: dict | None = None,
          values: dict | None = None, pandoc_args: list[str] | None = None) -> list[str]:
    """Markdown (or anything pandoc reads) -> .docx in the template's style. Returns warnings."""
    style = style or learn(template)
    with tempfile.TemporaryDirectory() as tmp:
        raw = os.path.join(tmp, "pandoc.docx")
        mark = os.path.join(tmp, "unnumbered.lua")
        Path(mark).write_text(UNNUMBERED_FILTER)
        subprocess.run(["pandoc", source, "--reference-doc", template, "--lua-filter", mark, "-o", raw,
                        *(pandoc_args or [])], check=True)
        return apply(template, raw, style, output, {**front_matter(source, tmp), **(values or {})})


def front_matter(source: str, tmp: str) -> dict[str, str]:
    """The document's metadata fields that are plain text, as pandoc reads them."""
    template = os.path.join(tmp, "meta.txt")
    Path(template).write_text("$meta-json$")
    out = subprocess.run(["pandoc", source, "-t", "plain", "--template", template],
                         check=True, capture_output=True, text=True).stdout
    return {k: v for k, v in json.loads(out or "{}").items() if isinstance(v, str)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="rework", description=__doc__)
    parser.add_argument("--version", action="version", version=f"rework {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p_learn = sub.add_parser("learn", help="print the house style rework found in a template (JSON)")
    p_learn.add_argument("template")

    p_build = sub.add_parser("build", help="build a document in the template's house style")
    p_build.add_argument("source", help="Markdown or any file pandoc can read")
    p_build.add_argument("-t", "--template", required=True, help="the client's .docx template or a past deliverable")
    p_build.add_argument("-o", "--output", required=True)
    p_build.add_argument("-s", "--style", help="style JSON from `rework learn` (edited if needed)")
    p_build.add_argument("--set", action="append", default=[], metavar="KEY=VALUE",
                         help="value for {KEY} in the style's cover replacements")
    p_build.add_argument("pandoc_args", nargs="*", help="extra pandoc arguments, after --")

    args = parser.parse_args(argv)
    if args.command == "learn":
        json.dump(learn(args.template), sys.stdout, indent=2, ensure_ascii=False)
        print()
        return 0

    bad = [item for item in args.set if "=" not in item]
    if bad:
        parser.error(f"--set needs KEY=VALUE, got {bad[0]!r}")
    values = dict(item.split("=", 1) for item in args.set)
    try:
        style = json.loads(Path(args.style).read_text()) if args.style else None
        warnings = build(args.source, args.template, args.output, style, values, args.pandoc_args)
    except FileNotFoundError as e:
        return _fail(f"no such file: {e.filename}")
    except json.JSONDecodeError as e:
        return _fail(f"{args.style} is not valid JSON: {e}")
    except subprocess.CalledProcessError:
        return _fail("pandoc failed (its error is above)")
    except ValueError as e:
        return _fail(str(e))
    for warning in warnings:
        print(f"rework: warning: {warning}", file=sys.stderr)
    print(f"rework: wrote {args.output}", file=sys.stderr)
    return 0


def _fail(message: str) -> int:
    print(f"rework: error: {message}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
