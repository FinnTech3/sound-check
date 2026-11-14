#!/usr/bin/env python3
"""record.py: run real commands and write a termcast cast JSON from their REAL output.

Usage: python3 record.py spec.json cast.json

spec.json:
{
  "title": "audio_probe.py",
  "cwd": "/tmp/sc-demo",                     where the commands run (a clean folder)
  "env": {"PYTHONUTF8": "1"},                optional extra environment
  "width": 990, "rows": 22, "wrap": 112,     optional, wrap = characters per line before hard wrapping
  "steps": [
    {"note": "# the hit should land on the cut at 1.20 s"},
    {"clear": true},                         wipe the screen (a new scene)
    {"cmd": "python3 audio_probe.py probe late.wav --cuts 1.20", "show": "python3 audio_probe.py probe late.wav --cuts 1.20",
     "maxLines": 14, "expectExit": [0, 1]},
    {"pause": 800}
  ]
}
"show" is what is displayed as the typed command (use it to shorten, never to change what runs).
If output is longer than maxLines the first maxLines are kept and a "... (N more lines)" line says so: nothing is faked.
A command whose exit code is not in expectExit (default [0]) makes this script fail loudly.
"""

import json
import os
import subprocess
import sys
import textwrap


def main() -> int:
    with open(sys.argv[1]) as fh:
        spec = json.load(fh)
    cast = {
        "title": spec.get("title", "terminal"),
        "width": spec.get("width", 940),
        "rows": spec.get("rows", 22),
        "fontSize": spec.get("fontSize", 15),
        "typeSeconds": spec.get("typeSeconds", 3),
        "highlight": spec.get("highlight", []),
        "steps": [],
    }
    wrap = spec.get("wrap", 98)
    env = dict(os.environ)
    env.update(spec.get("env", {}))
    env.setdefault("COLUMNS", str(wrap))
    env.setdefault("PYTHONUTF8", "1")
    env.setdefault("NO_COLOR", "1")
    for st in spec["steps"]:
        if st.get("clear"):
            cast["steps"].append({"type": "clear"})
        elif "note" in st:
            cast["steps"].append({"type": "note", "text": st["note"]})
        elif "pause" in st:
            cast["steps"].append({"type": "pause", "ms": st["pause"]})
        elif "cmd" in st:
            p = subprocess.run(
                ["bash", "-c", st["cmd"]],
                cwd=spec["cwd"],
                env=env,
                capture_output=True,
                text=True,
                timeout=st.get("timeout", 120),
            )
            if p.returncode not in st.get("expectExit", [0]):
                print(f"command failed ({p.returncode}): {st['cmd']}\n{p.stdout}\n{p.stderr}", file=sys.stderr)
                return 1
            out = (p.stdout + p.stderr).rstrip("\n")
            lines = []
            for ln in out.split("\n"):
                wrapped = textwrap.wrap(ln, wrap, replace_whitespace=False, drop_whitespace=False, subsequent_indent="  ")
                lines.extend(wrapped or [""])
            mx = st.get("maxLines")
            if mx and len(lines) > mx:
                more = len(lines) - mx
                lines = lines[:mx] + [f"... ({more} more lines)"]
            cast["steps"].append({"type": "cmd", "text": st.get("show", st["cmd"])})
            if lines:
                cast["steps"].append({"type": "out", "text": "\n".join(lines), "holdSeconds": st.get("hold", 1.4)})
    with open(sys.argv[2], "w") as fh:
        json.dump(cast, fh, indent=1)
    print(f"wrote {sys.argv[2]}: {len(cast['steps'])} steps")
    return 0


if __name__ == "__main__":
    sys.exit(main())
