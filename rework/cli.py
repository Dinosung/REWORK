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


def build(source: str, template: str, output: str, style: dict | None = None,
          values: dict | None = None, pandoc_args: list[str] | None = None) -> list[str]:
    """Markdown (or anything pandoc reads) -> .docx in the template's style."""
    style = style or learn(template)
    with tempfile.TemporaryDirectory() as tmp:
        raw = os.path.join(tmp, "pandoc.docx")
        subprocess.run(["pandoc", source, "--reference-doc", template, "-o", raw, *(pandoc_args or [])],
                       check=True)
        return apply(template, raw, style, output, values)


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
        json.dump(learn(args.template), sys.stdout, indent=2)
        print()
        return 0

    style = json.loads(Path(args.style).read_text()) if args.style else None
    values = dict(item.split("=", 1) for item in args.set)
    missing = build(args.source, args.template, args.output, style, values, args.pandoc_args)
    if missing:
        print(f"rework: warning: styles still undefined: {', '.join(missing)}", file=sys.stderr)
    print(f"rework: wrote {args.output}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
