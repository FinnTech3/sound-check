#!/usr/bin/env python3
"""Check a skill folder against Agensi's packaging and security-scan rules, then zip it.

Usage:
    python3 tools/agensi_build.py                 # check the folder under agensi/ and write dist/<name>.zip
    python3 tools/agensi_build.py PATH --check    # check only
    python3 tools/agensi_build.py PATH --with skills   # also pack another folder (a skill pack)

The rules mirror https://www.agensi.io/docs/packaging, /docs/review-and-approval and
/docs/submit-on-the-website, plus quality checks drawn from Agensi's creator guides.
It also checks agensi/LISTING.md (the text you paste into the submit form) when that file exists.
A FAIL here is something Agensi's scan fails; a WARN costs scan points or review time.
Exit codes: 0 clean (warnings allowed), 1 a check failed, 2 usage error.
"""

from __future__ import annotations

import argparse
import re
import sys
import zipfile
from pathlib import Path

EXECUTABLES = {".exe", ".dll", ".so", ".dylib", ".bin", ".app", ".dmg", ".msi", ".deb", ".rpm", ".wasm", ".class"}
EXECUTABLES |= {".jar", ".war"}
BUNDLED = {"node_modules", "site-packages", ".venv", "venv"}
SKIP = {".git", "__pycache__", ".DS_Store", "__MACOSX", ".pytest_cache", ".ruff_cache"}
SCRIPT_EXT = {".py", ".sh", ".js", ".mjs", ".ts", ".rb", ".ps1"}
MAX_FILES, MAX_CHARS, MAX_ZIP, MAX_SKILLS, SCRIPT_BYTES = 200, 6_000_000, 50 * 1024 * 1024, 50, 20 * 1024
CATEGORIES = {
    "Agents & Orchestration", "Prompt & Skill Engineering", "LLM Ops", "Frontend & Web Apps", "Mobile Development",
    "APIs & Backend", "Code Quality & Review", "Testing & Debugging", "DevOps & Cloud", "Data & Databases",
    "Web3 & Crypto", "Security", "Technical Documentation", "Marketing & SEO", "Sales & Lead Gen", "Social Media",
    "E-commerce", "Digital Products", "Research & Analysis", "Business & Operations", "Product Management",
    "Workflow Automation", "Productivity", "Finance & Accounting", "Legal & Compliance", "Trading & Investing",
    "HR & Recruiting", "Writing & Content", "Branding & Design", "UX & UI Design", "Image & Video",
    "Education & Learning", "Translation & Localization", "Game Development",
}  # fmt: skip
OUTSIDE_CHECKOUT = (
    r"(?i)gumroad|whop\.com|lemonsqueezy|lemon squeezy|payhip|ko-fi|patreon|buy\.stripe\.com|checkout\.stripe\.com"
)
RUNS_SCRIPT = r"(?m)^\s*(\$\s*)?(python3?|bash|sh|node)\s+(\./)?(shared/)?scripts/"

FAIL_PATTERNS = [
    ("dangerous command", r"rm\s+-[a-z]*r[a-z]*f?\s+/(?![\w.])"),
    ("dangerous command", r"(curl|wget)\b[^\n|]*\|\s*(sudo\s+)?(ba|z)?sh\b"),
    ("dangerous command", r"\bos\.system\s*\("),
    ("dangerous command", r"shell\s*=\s*True"),
    ("dangerous command", r"chmod\s+(-R\s+)?777"),
    ("secret", r"AKIA[0-9A-Z]{16}"),
    ("secret", r"\b(sk|rk)-[A-Za-z0-9_-]{24,}"),
    ("secret", r"\bgh[pousr]_[A-Za-z0-9]{30,}"),
    ("secret", r"\bxox[abprs]-[A-Za-z0-9-]{10,}"),
    ("secret", r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    ("secret", r"(?i)\b(password|passwd|api[_-]?key|secret|token)\b\s*[:=]\s*['\"][^'\"\s{}<>$]{8,}['\"]"),
    ("obfuscation", r"b64decode\s*\(|\batob\s*\(|fromCharCode\s*\("),
    ("obfuscation", r"\b(eval|exec)\s*\(\s*(compile|bytes|base64|codecs|__import__)"),
    ("prompt injection", r"(?i)ignore (all )?(the )?(previous|prior|above) instructions"),
    ("prompt injection", r"(?i)do not tell the user|don't tell the user|without telling the user"),
    ("prompt injection", r"(?i)\bsecretly\b|disregard (your|the) (instructions|rules)"),
]
WARN_PATTERNS = [
    ("uses curl", r"\bcurl\b"),
    ("uses sudo", r"\bsudo\b"),
    ("uses base64", r"(?i)\bbase64\b"),
    ("personal path", r"/home/[a-z]\w+/|/Users/\w+/|C:\\Users\\"),
    ("email address", r"\b[\w.+-]+@(?!example\.(com|org|net)\b)[\w-]+\.[a-z]{2,}\b"),
]
NETWORK = r"urllib\.request|\brequests\.(get|post)|http\.client|\bsocket\.|\bfetch\s*\(|https?\.request"
LOCAL_READ = r"\bopen\s*\(|\.read_text\s*\(|\.read_bytes\s*\(|readFileSync|readFile\s*\(|\bcat\s+[~/.]"
ENV = r"os\.environ|os\.getenv|process\.env|\$\{?[A-Z_]{3,}\}?\s"
WRITES = r"open\s*\([^)]*['\"][wa]b?['\"]|\.write_(text|bytes)\s*\(|writeFileSync"
SHELL_REDIRECT = r">>?\s*[\w./~-]+\s*$"


def list_count(text: str, key: str) -> int:
    """Entries in a frontmatter list written inline ([a, b]) or as '- item' lines."""
    lines = text.split("\n---", 1)[0].splitlines()
    for i, line in enumerate(lines):
        if re.match(rf"^{key}:", line):
            inline = line.split(":", 1)[1].strip()
            if inline.startswith("["):
                return len([x for x in inline.strip("[]").split(",") if x.strip()])
            count = 0
            for nxt in lines[i + 1 :]:
                if re.match(r"^\s*-\s+\S", nxt):
                    count += 1
                elif nxt.strip() and not nxt.startswith(" "):
                    break
            return count
    return 0


def check_listing(path: Path) -> list[tuple[str, str, str]]:
    """Check the marketplace form text in LISTING.md: field limits and required sections."""
    text = path.read_text(encoding="utf-8")
    out: list[tuple[str, str, str]] = []
    rows = dict(re.findall(r"(?m)^\|\s*([A-Za-z ]+?)\s*\|\s*(.+?)\s*\|\s*$", text))
    sections = {m.group(1).strip().lower(): m.group(2) for m in re.finditer(r"(?ms)^## (.+?)\n(.*?)(?=^## |\Z)", text)}
    where = str(path)

    def fail(msg: str, level: str = "FAIL") -> None:
        out.append((level, where, msg))

    title = rows.get("Title", "")
    if not title:
        fail("no Title row")
    elif len(title) > 60:
        fail(f"title is {len(title)} characters; Agensi allows 60")
    cats = [
        c.strip() for c in re.split(r"[;,]|\bthen\b", rows.get("Categories", rows.get("Category", ""))) if c.strip()
    ]
    if not cats:
        fail("no Categories row (up to 3 of Agensi's 32)")
    elif len(cats) > 3 or any(c not in CATEGORIES for c in cats):
        fail(f"categories must be at most 3 names from Agensi's list; got {cats}")
    price = re.search(r"\$(\d+(?:\.\d+)?)", rows.get("Suggested price", ""))
    if rows.get("Suggested price") and not price and "free" not in rows["Suggested price"].lower():
        fail("suggested price is neither free nor a dollar amount")
    if price and not 1 <= float(price.group(1)) <= 50:
        fail("suggested price outside $1 to $50; $5 to $20 converts best", "WARN")
    if not rows.get("Compatibility note"):
        fail("no Compatibility note row (what it needs, for example 'Requires Python 3.10+')")
    if not rows.get("Permissions"):
        fail("no Permissions row: check them against what the upload form detects")
    summary = sections.get("summary", sections.get("one-line summary", "")).strip()
    if not summary:
        fail("no Summary section")
    elif len(summary) > 300:
        fail(f"summary is {len(summary)} characters; Agensi allows 300")
    if len(sections.get("description", "").strip()) < 600:
        fail("Description is under 600 characters: say what it does, how it works and where it stops")
    for needed in ("limitations", "faq"):
        if needed not in sections:
            fail(
                f"no '{needed.upper() if needed == 'faq' else needed.capitalize()}' section (optional on Agensi, recommended)",
                "WARN",
            )
    demo = sections.get("see it in action", "")
    if len(demo.strip()) < 700:
        fail(
            f"'See it in action' is {len(demo.strip())} characters; a real request and the full result, 700+ works best"
        )
    media = path.parent / "media"
    logo = media / "logo.png"
    if not logo.is_file():
        fail("no agensi/media/logo.png (square, 512 x 512 recommended, up to 5 MB)", "WARN")
    else:
        head = logo.read_bytes()[:24]
        size = (
            (int.from_bytes(head[16:20], "big"), int.from_bytes(head[20:24], "big"))
            if head[:8] == b"\x89PNG\r\n\x1a\n"
            else None
        )
        if size is None:
            fail("logo.png is not a PNG file")
        elif size[0] != size[1]:
            fail(f"logo is {size[0]} x {size[1]}; it must be square (512 x 512 recommended)")
        elif size[0] < 256:
            fail(f"logo is {size[0]} px wide; use 512 x 512", "WARN")
        if logo.stat().st_size > 5 * 1024 * 1024:
            fail("logo is over 5 MB")
    shots = sorted(media.glob("screenshot-*.png")) if media.is_dir() else []
    if not shots:
        fail("no agensi/media/screenshot-1.png (up to 6 screenshots of 10 MB each)", "WARN")
    if len(shots) > 6 or any(s.stat().st_size > 10 * 1024 * 1024 for s in shots):
        fail("at most 6 screenshots of 10 MB each")
    if re.search(OUTSIDE_CHECKOUT, text):
        fail("outside checkout or paid-version link is banned")
    if re.search(r"\bTODO\b|\bTBD\b", text):
        fail("unfinished marker", "WARN")
    return out


def _skipped(rel: Path) -> bool:
    """Build leftovers that Agensi strips or that must never ship."""
    return bool(SKIP & set(rel.parts)) or rel.suffix == ".pyc" or any(p.endswith(".egg-info") for p in rel.parts)


def yaml_problems(text: str) -> list[str]:
    """Strict checks a real YAML parser would make, without needing one: an unquoted value may not hold ': ' or ' #'."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return []
    end = next((i for i, ln in enumerate(lines[1:], 1) if ln.strip() == "---"), None)
    if end is None:
        return ["frontmatter is not closed with ---"]
    found, in_block = [], False
    for number, line in enumerate(lines[1:end], 2):
        m = re.match(r"^([A-Za-z_][\w-]*):\s*(.*)$", line)
        if m:
            value = m.group(2).strip()
            in_block = value in (">", "|", ">-", "|-", ">+", "|+")
            if in_block or not value or value[0] in "\"'[{":
                continue
            if ": " in value or " #" in value or value.endswith(":"):
                found.append(
                    f"line {number}: unquoted value contains ': ' or ' #', which is invalid YAML; quote it or use a '>' block"
                )
        elif line.startswith((" ", "\t")) and not in_block:
            item = line.strip().lstrip("- ").strip()
            if item and item[0] not in "\"'[{" and (": " in item or " #" in item):
                found.append(f"line {number}: list item contains ': ' or ' #'; quote it")
    return found


def frontmatter(text: str) -> dict[str, str] | None:
    """Parse the top-level keys of a YAML frontmatter block. Folded and literal scalars are joined."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    try:
        end = next(i for i, ln in enumerate(lines[1:], 1) if ln.strip() == "---")
    except StopIteration:
        return None
    data: dict[str, str] = {}
    key = None
    for ln in lines[1:end]:
        m = re.match(r"^([A-Za-z_][\w-]*):\s*(.*)$", ln)
        if m:
            key, value = m.group(1), m.group(2).strip()
            data[key] = "" if value in (">", "|", ">-", "|-") else value.strip("'\"")
        elif key and ln.strip():
            data[key] = (data[key] + " " + ln.strip().lstrip("- ")).strip()
    return data


def collect(root: Path, extras: list[Path] = ()) -> tuple[list[tuple[Path, Path]], list[tuple[str, str, str]]]:
    """List (file, path inside the zip) for root and each extra folder, plus structural findings."""
    out: list[tuple[str, str, str]] = []
    files: list[tuple[Path, Path]] = []
    for base, prefix in [(root, Path())] + [(e, Path(e.name)) for e in extras]:
        for p in sorted(base.rglob("*")):
            rel = prefix / p.relative_to(base)
            if _skipped(rel):
                continue
            if BUNDLED & set(rel.parts):
                out.append(("FAIL", rel.as_posix(), "bundled dependencies are not allowed"))
            elif p.is_symlink():
                out.append(("FAIL", rel.as_posix(), "symlinks are not allowed"))
            elif p.is_file():
                files.append((p, rel))
    return files, out


def check(root: Path, extras: list[Path] = ()) -> list[tuple[str, str, str]]:
    """Return (level, path, message) findings for the skill or skill pack at root."""
    files, out = collect(root, extras)

    skills = [(p, rel) for p, rel in files if p.name == "SKILL.md"]
    if not skills:
        out.append(("FAIL", ".", "no SKILL.md found"))
    if len(skills) > MAX_SKILLS:
        out.append(("FAIL", ".", f"{len(skills)} skills; a pack holds at most {MAX_SKILLS}"))
    names: set[str] = set()
    for sk, sk_rel in skills:
        rel, text = sk_rel.as_posix(), sk.read_text(encoding="utf-8", errors="replace")
        fm = frontmatter(text)
        if fm is None:
            out.append(("FAIL", rel, "missing or unclosed YAML frontmatter"))
            continue
        for problem in yaml_problems(text):
            out.append(("FAIL", rel, f"invalid YAML in frontmatter, {problem}"))
        name, desc = fm.get("name", ""), fm.get("description", "")
        if not name:
            out.append(("FAIL", rel, "frontmatter has no name"))
        if name in names:
            out.append(("FAIL", rel, f"duplicate skill name '{name}'"))
        names.add(name)
        if not desc:
            out.append(("FAIL", rel, "frontmatter has no description"))
        elif "use when" not in desc.lower():
            out.append(("WARN", rel, "description has no 'Use when ...' trigger phrases"))
        if desc and not re.search(r"(?i)\bdo not use\b|\bnot for\b|\bnot use\b|\bdon't use\b", desc):
            out.append(("WARN", rel, "description has no negative trigger ('Do not use for ...')"))
        if len(name) > 60:
            out.append(("FAIL", rel, f"name is {len(name)} characters; Agensi allows 60"))
        if not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", name or "x"):
            out.append(("WARN", rel, "name is not a lower-case slug such as code-reviewer"))
        single = len(skills) == 1  # a pack's listing fields live in LISTING.md; each skill needs name + description
        summary = fm.get("summary", "")
        if not summary and single:
            out.append(("WARN", rel, "frontmatter has no summary (the form reads it; 300 characters at most)"))
        elif len(summary) > 300:
            out.append(("FAIL", rel, f"summary is {len(summary)} characters; Agensi allows 300"))
        for field in ("version", "tags", "keywords", "use_cases", "docs_url"):
            if field not in fm and single:
                out.append(("WARN", rel, f"frontmatter has no {field} (the upload form reads it)"))
        if not re.fullmatch(r"\d+(\.\d+)*", fm.get("version", "1")):
            out.append(("FAIL", rel, "version must be numbers and dots only"))
        for field, limit in (("tags", 10), ("keywords", 10), ("use_cases", 8)):
            count = list_count(text, field)
            if count > limit:
                out.append(("FAIL", rel, f"{field} has {count} entries; Agensi allows {limit}"))
        if len(desc) > 1024:
            out.append(("WARN", rel, f"description is {len(desc)} characters; keep it under 1024"))
        body = text.split("---", 2)[2] if text.count("---") >= 2 else ""
        if len(body.strip()) < 200:
            out.append(("FAIL", rel, "SKILL.md has no real instructions after the frontmatter"))
        skill_dirs = [s.parent for s, _ in skills]
        shared = [p for p, _ in files if p.suffix in SCRIPT_EXT and not any(d in p.parents for d in skill_dirs)]
        scripts_here = bool(shared) or any(p.suffix in SCRIPT_EXT and sk.parent in p.parents for p, _ in files)
        if scripts_here:
            if not re.search(r"(?m)^\*{0,2}Requires:?\*{0,2}:?\s", body) and "Requires:" not in body:
                out.append(("WARN", rel, "scripts present but no 'Requires:' line: agents read it to warn the buyer"))
            if re.search(RUNS_SCRIPT, body) and "temporary file" not in body.lower():
                out.append(
                    (
                        "FAIL",
                        rel,
                        "runs scripts/ by path, but Agensi delivers scripts as text: tell the agent to "
                        "write the script unchanged to a temporary file, run it, then delete it",
                    )
                )
        if not re.search(r"(?im)^#{1,3}\s*(output|output format|reporting back|what to return|deliverable)", body):
            out.append(("WARN", rel, "no output-format heading: define exactly what the agent hands back"))
        if not re.search(r"(?im)^#{1,3}\s*.*(edge case|errors|fallback|when to stop|failure)", body):
            out.append(("WARN", rel, "no edge-case or error-handling section"))
        if text.count("\n") > 500:
            out.append(
                ("WARN", rel, f"{text.count(chr(10))} lines; keep SKILL.md under 500 and move detail to references/")
            )

    top = {p_rel.parts[0] if len(p_rel.parts) > 1 else "" for _, p_rel in files}
    if "README.md" not in {r.name for _, r in files if len(r.parts) <= 2}:
        out.append(("WARN", ".", "no README.md: a short buyer-facing README raises buyer confidence"))
    if not ({"examples", "references"} & top) and len(skills) == 1:
        out.append(("WARN", ".", "no examples/ or references/ folder: skills with supporting files sell better"))
    for p, p_rel in files:
        if p.name.startswith(".") and p.name != ".env.example":
            out.append(("WARN", p_rel.as_posix(), "hidden file: Agensi strips some of these; remove it"))

    all_bodies = " ".join(sk.read_text(encoding="utf-8", errors="replace").lower() for sk, _ in skills)
    chars, others = 0, 0
    for p, p_rel in files:
        rel = p_rel.as_posix()
        if p.suffix.lower() in EXECUTABLES:
            out.append(("FAIL", rel, "executable file types are rejected"))
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            out.append(("WARN", rel, "not a text file: agents cannot read it"))
            continue
        chars += len(text)
        others += p.name != "SKILL.md"
        m = re.search(OUTSIDE_CHECKOUT, text)
        if m:
            out.append(("FAIL", rel, f"outside checkout or paid-version link: {m.group(0)!r} is banned"))
        m = re.search(r"\b(TODO|FIXME|TBD|lorem ipsum)\b", text)
        if m and p.name in ("SKILL.md", "README.md", "LISTING.md"):
            out.append(("WARN", rel, f"unfinished marker {m.group(0)!r}"))
        for label, pattern in FAIL_PATTERNS:
            m = re.search(pattern, text)
            if m:
                line = text.count("\n", 0, m.start()) + 1
                out.append(("FAIL", f"{rel}:{line}", f"{label}: {m.group(0)[:50]!r}"))
        for label, pattern in WARN_PATTERNS:
            m = re.search(pattern, text)
            if m:
                out.append(("WARN", f"{rel}:{text.count(chr(10), 0, m.start()) + 1}", label))
        if p.suffix in SCRIPT_EXT:
            net = re.search(NETWORK, text)
            if net and re.search(LOCAL_READ, text):
                out.append(("FAIL", rel, "network calls combined with reading local data"))
            if net and re.search(ENV, text):
                out.append(("FAIL", rel, "reads environment variables and makes network calls"))
            if re.search(WRITES, text) or (p.suffix == ".sh" and re.search(SHELL_REDIRECT, text, re.M)):
                out.append(("WARN", rel, "writes files"))
            if net and "network" not in all_bodies:
                out.append(("WARN", rel, "makes network calls: say why in SKILL.md"))
            if len(text.encode()) > SCRIPT_BYTES:
                out.append(
                    ("WARN", rel, f"script is {len(text.encode()) // 1024} KB; Agensi suggests under 20 KB of logic")
                )
            if not text.lstrip().startswith(("#", '"""', "//", "/*")):
                out.append(("WARN", rel, "script has no leading comment explaining what it does"))
    if others > MAX_FILES:
        out.append(("FAIL", ".", f"{others} supporting files; agents receive at most {MAX_FILES}"))
    if chars > MAX_CHARS:
        out.append(("FAIL", ".", f"{chars:,} characters; the limit is {MAX_CHARS:,} per listing"))
    return out


def build_zip(root: Path, out_dir: Path, extras: list[Path] = ()) -> Path:
    """Write <out_dir>/<root name>.zip with one top-level folder."""
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"{root.name}.zip"
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zf:
        for p, rel in collect(root, extras)[0]:
            zf.write(p, Path(root.name) / rel)
    return target


def default_root() -> Path | None:
    base = Path("agensi")
    found = [p for p in base.iterdir() if p.is_dir() and p.name != "media"] if base.is_dir() else []
    return found[0] if len(found) == 1 else None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument(
        "path", nargs="?", help="skill folder (default: the only folder under agensi/, not counting media/)"
    )
    ap.add_argument("--check", action="store_true", help="check only, do not write a zip")
    ap.add_argument("--out", default="dist", help="folder for the zip (default: dist)")
    ap.add_argument("--with", dest="extras", action="append", default=[], help="extra folder to pack beside it")
    args = ap.parse_args(argv)
    root = Path(args.path) if args.path else default_root()
    if root is None or not root.is_dir():
        print("error: give the skill folder, or keep exactly one skill folder under agensi/", file=sys.stderr)
        return 2
    extras = [Path(e) for e in args.extras]
    if any(not e.is_dir() for e in extras):
        print("error: every --with value must be a folder", file=sys.stderr)
        return 2
    findings = check(root, extras)
    listing = root.parent / "LISTING.md"
    if listing.is_file():
        findings += check_listing(listing)
    else:
        findings.append(("WARN", str(root.parent), "no LISTING.md: write the form text before you submit"))
    for level, where, message in findings:
        print(f"{level}  {where}: {message}")
    fails = sum(1 for f in findings if f[0] == "FAIL")
    warns = len(findings) - fails
    print(f"{root}: {fails} failed, {warns} warning(s), estimated scan score {max(0, 100 - 20 * fails - 5 * warns)}")
    if fails:
        return 1
    if not args.check:
        target = build_zip(root, Path(args.out), extras)
        size = target.stat().st_size
        if size > MAX_ZIP:
            print(f"FAIL  {target}: {size:,} bytes; the upload limit is 50 MB")
            return 1
        print(f"wrote {target} ({size:,} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
