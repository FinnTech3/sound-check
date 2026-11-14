"""The skill folder as a buyer receives it: checker clean, zip layout, frontmatter, scripts standalone."""

import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

import agensi_build as ab

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "agensi" / "sound-check"
SCRIPTS = sorted((SKILL / "scripts").glob("*.py"))


def test_checker_finds_nothing_to_fail_or_warn_about():
    assert ab.check(SKILL) == []
    assert ab.check_listing(ROOT / "agensi" / "LISTING.md") == []


def test_zip_has_one_top_folder_and_no_leftovers(tmp_path):
    names = zipfile.ZipFile(ab.build_zip(SKILL, tmp_path)).namelist()
    assert {n.split("/")[0] for n in names} == {"sound-check"}
    assert "sound-check/SKILL.md" in names and not [n for n in names if "__pycache__" in n or "cache" in n]
    assert not [n for n in names if n.endswith((".png", ".exe"))]


@pytest.mark.parametrize("script", SCRIPTS, ids=lambda p: p.name)
def test_each_script_fits_the_size_budget_and_has_no_imports_of_siblings(script):
    text = script.read_text()
    assert len(text.encode()) <= 20 * 1024
    assert "import audio_probe" not in text and "import sfx_synth" not in text
    assert not any(bad in text for bad in ("shell=True", "os.system", "eval(", "urllib", "socket", "subprocess"))


def test_frontmatter_parses_with_a_real_yaml_parser():
    yaml = pytest.importorskip("yaml")
    meta = yaml.safe_load((SKILL / "SKILL.md").read_text().split("---")[1])
    assert meta["name"] == "sound-check" and meta["version"] == "1.0.0"
    assert len(meta["description"]) < 1024 and len(meta["summary"]) <= 300
    assert "Use when" in meta["description"] and "Do not use for" in meta["description"]
    assert meta["docs_url"] == "https://github.com/FinnTech3/sound-check"


def test_skill_md_tells_the_agent_to_use_temporary_files():
    text = (SKILL / "SKILL.md").read_text()
    assert "temporary file" in text and 'python3 "$PROBE"' in text and 'python3 "$SYNTH"' in text
    assert "python3 scripts/" not in text and "Requires:" in text


@pytest.mark.parametrize("script", SCRIPTS, ids=lambda p: p.name)
def test_scripts_run_alone_from_an_empty_folder(tmp_path, script):
    done = subprocess.run([sys.executable, str(script), "--help"], cwd=tmp_path, capture_output=True, text=True)
    assert done.returncode == 0 and "usage:" in done.stdout
