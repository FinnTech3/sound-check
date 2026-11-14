"""sfx_synth: every preset renders, is deterministic, honours its parameters and never touches other files."""

import contextlib
import io
import json
import re
import struct
import subprocess
import sys
import wave
from pathlib import Path

import pytest

import sfx_synth
from conftest import write_wav

SCRIPT = Path(sfx_synth.__file__)
NOISY = ["click", "whoosh", "riser", "hit", "thump"]
PRESETS = list(sfx_synth.PRESETS)


def make(tmp_path, preset, *args, name=None):
    """Run `make` with its report swallowed, so a probe in the same test reads only its own output."""
    out = tmp_path / (name or f"{preset}.wav")
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        code = sfx_synth.main(["make", preset, "--out", str(out), *args])
    return code, out


def test_nine_presets_exist():
    assert PRESETS == ["click", "tick", "pop", "thump", "whoosh", "riser", "hit", "chime", "drop"]


def test_list_shows_every_preset_and_parameter(capsys):
    assert sfx_synth.main(["list"]) == 0
    text = capsys.readouterr().out
    for name, (_, _, params) in sfx_synth.PRESETS.items():
        assert f"{name}:" in text
        assert all(f"{p}=" in text for p in params)
    assert "level_db" in text and "delay_ms" in text


def test_list_json_is_valid_and_complete(capsys):
    assert sfx_synth.main(["list", "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert list(data["presets"]) == PRESETS and "level_db" in data["common_params"]
    assert data["presets"]["chime"]["params"]["tone_hz"]["default"] == 880.0


@pytest.mark.parametrize("preset", PRESETS)
def test_each_preset_writes_a_valid_wav_at_the_default_level(tmp_path, preset, probe):
    code, out = make(tmp_path, preset)
    assert code == 0
    with wave.open(str(out), "rb") as w:  # the standard library's own reader must accept it
        assert (w.getnchannels(), w.getsampwidth(), w.getframerate()) == (1, 2, 44100)
        assert w.getnframes() == round(sfx_synth.PRESETS[preset][1] * 44100)
    _, r, _ = probe(out)
    assert r["level"]["peak_dbfs"] == pytest.approx(-6.0, abs=0.02) and r["findings"] == []
    assert r["clipping"]["runs"] == 0 and r["level"]["dc_offset"] < 0.01 and r["summary"] != "silent"


@pytest.mark.parametrize("preset", PRESETS)
def test_same_inputs_give_identical_bytes(tmp_path, preset):
    _, a = make(tmp_path, preset, "--seed", "7", name="a.wav")
    _, b = make(tmp_path, preset, "--seed", "7", name="b.wav")
    assert a.read_bytes() == b.read_bytes()


@pytest.mark.parametrize("preset", NOISY)
def test_noise_presets_change_with_the_seed(tmp_path, preset):
    _, a = make(tmp_path, preset, "--seed", "1", name="a.wav")
    _, b = make(tmp_path, preset, "--seed", "2", name="b.wav")
    assert a.read_bytes() != b.read_bytes()


def test_tonal_presets_ignore_the_seed(tmp_path):
    _, a = make(tmp_path, "chime", "--seed", "1", name="a.wav")
    _, b = make(tmp_path, "chime", "--seed", "99", name="b.wav")
    assert a.read_bytes() == b.read_bytes()


def test_default_seed_is_fixed_not_random(tmp_path):
    _, a = make(tmp_path, "whoosh", name="a.wav")
    _, b = make(tmp_path, "whoosh", "--seed", "1", name="b.wav")
    assert a.read_bytes() == b.read_bytes()


def test_the_script_has_no_unseeded_randomness():
    text = SCRIPT.read_text()
    assert not re.search(r"\brandom\.(random|uniform|gauss|randint|choice|seed|shuffle)\s*\(", text)
    assert "time.time" not in text and "os.urandom" not in text and "secrets" not in text


def test_level_param_sets_the_peak(tmp_path, probe):
    _, out = make(tmp_path, "tick", "--param", "level_db=-18")
    assert probe(out)[1]["level"]["peak_dbfs"] == pytest.approx(-18.0, abs=0.02)


def test_a_level_above_zero_clips_on_purpose(tmp_path, probe, capsys):
    out = tmp_path / "hot.wav"
    assert sfx_synth.main(["make", "thump", "--out", str(out), "--param", "level_db=8"]) == 0
    assert re.search(r"[1-9]\d* samples at full scale", capsys.readouterr().out)
    code, r, _ = probe(out)
    assert code == 1 and r["clipping"]["runs"] > 0 and any(f["kind"] == "clipping" for f in r["findings"])


def test_delay_moves_the_onset_and_the_leading_silence(tmp_path, probe):
    _, out = make(tmp_path, "hit", "--param", "delay_ms=250", "--duration", "1.5")
    _, r, _ = probe(out)
    assert r["silence"]["leading_s"] == pytest.approx(0.25, abs=0.006)
    assert r["events"]["onsets_s"][0] == pytest.approx(0.25, abs=0.006)
    assert r["format"]["duration_s"] == 1.5


def test_duration_sets_the_file_length(tmp_path):
    _, out = make(tmp_path, "click", "--duration", "0.5")
    with wave.open(str(out), "rb") as w:
        assert w.getnframes() == 22050


@pytest.mark.parametrize("rate", [22050, 48000, 96000])
def test_other_sample_rates(tmp_path, probe, rate):
    _, out = make(tmp_path, "chime", "--rate", str(rate))
    _, r, _ = probe(out)
    assert r["format"]["sample_rate"] == rate and r["spectrum"]["strongest_hz"] == pytest.approx(880, abs=15)


@pytest.mark.parametrize(("decay", "tol"), [(150, 30), (500, 40), (1200, 60)])
def test_decay_param_is_what_the_probe_measures(tmp_path, probe, decay, tol):
    _, out = make(tmp_path, "chime", "--param", f"decay_ms={decay}", "--duration", "3.5")
    assert probe(out)[1]["events"]["decay_ms"] == pytest.approx(decay, abs=tol)


def test_pitch_param_is_what_the_probe_hears(tmp_path, probe):
    for hz in (440, 1320, 3000):
        _, out = make(tmp_path, "tick", "--param", f"tone_hz={hz}", name=f"t{hz}.wav")
        assert probe(out)[1]["spectrum"]["strongest_hz"] == pytest.approx(hz, rel=0.03)


def test_the_probe_tells_the_presets_apart(tmp_path, probe):
    said = {}
    for preset in ("click", "whoosh", "chime", "riser", "thump"):
        _, out = make(tmp_path, preset)
        said[preset] = probe(out)[1]["summary"]
    assert said["click"].startswith("very short click")
    assert "swell" in said["whoosh"] and "noise-like" in said["whoosh"]
    assert "tonal near 88" in said["chime"] and "long-tailed" in said["chime"]
    assert "swell" in said["riser"] and "sweeping" in said["riser"]
    assert "dark" in said["thump"]


def test_a_late_hit_is_caught_by_the_sync_check_and_fixed_by_delay(tmp_path, probe):
    _, late = make(tmp_path, "hit", "--param", "delay_ms=1280", "--duration", "3", name="late.wav")
    code, r, _ = probe(late, "--cuts", "1.2")
    assert code == 1 and r["sync"]["cuts"][0]["offset_ms"] == pytest.approx(80, abs=3)
    _, fixed = make(tmp_path, "hit", "--param", "delay_ms=1200", "--duration", "3", name="fixed.wav")
    code, r, _ = probe(fixed, "--cuts", "1.2")
    assert code == 0 and abs(r["sync"]["cuts"][0]["offset_ms"]) <= 3


def test_refuses_to_overwrite_and_leaves_the_file_alone(tmp_path, capsys):
    original = write_wav(tmp_path / "mine.wav", [[0.1, 0.2, 0.3]])
    before = original.read_bytes()
    code = sfx_synth.main(["make", "click", "--out", str(original)])
    assert code == 2 and "already exists" in capsys.readouterr().err
    assert original.read_bytes() == before


def test_force_replaces_an_existing_file(tmp_path):
    out = tmp_path / "x.wav"
    out.write_bytes(b"old")
    assert sfx_synth.main(["make", "click", "--out", str(out), "--force"]) == 0
    assert out.read_bytes()[:4] == b"RIFF"


def test_writes_only_the_file_it_was_given(tmp_path):
    (tmp_path / "keep.txt").write_text("keep")
    before = {p.name for p in tmp_path.iterdir()}
    make(tmp_path, "pop", name="only.wav")
    assert {p.name for p in tmp_path.iterdir()} == before | {"only.wav"}
    assert (tmp_path / "keep.txt").read_text() == "keep"


def test_a_missing_folder_is_an_error_not_a_new_folder(tmp_path, capsys):
    code = sfx_synth.main(["make", "click", "--out", str(tmp_path / "nope" / "x.wav")])
    assert code == 2 and "cannot write" in capsys.readouterr().err and not (tmp_path / "nope").exists()


@pytest.mark.parametrize(
    "args",
    [["--param", "nonsense=1"], ["--param", "decay_ms"], ["--param", "decay_ms=abc"], ["--param", "decay_ms=0"],
     ["--param", "decay_ms=nan"], ["--param", "decay_ms=inf"], ["--param", "ring_hz=30000"], ["--param", "noise=2"],
     ["--duration", "0"], ["--duration", "61"], ["--duration", "0.2", "--param", "delay_ms=195"],
     ["--rate", "100"], ["--rate", "200000"], ["--rate", "22050", "--param", "ring_hz=12000"]],
)
def test_bad_input_is_exit_2_with_one_line(tmp_path, capsys, args):
    out = tmp_path / "click.wav"
    assert sfx_synth.main(["make", "click", "--out", str(out), *args]) == 2
    err = capsys.readouterr().err
    assert err.startswith("error:") and err.count("\n") == 1 and not out.exists()


def test_unknown_preset_lists_the_valid_ones(tmp_path, capsys):
    out = tmp_path / "boing.wav"
    assert sfx_synth.main(["make", "boing", "--out", str(out)]) == 2
    assert "click" in capsys.readouterr().err and not out.exists()


def test_a_parameter_from_another_preset_is_refused(tmp_path, capsys):
    assert sfx_synth.main(["make", "click", "--out", str(tmp_path / "c.wav"), "--param", "body_hz=60"]) == 2
    assert "no parameter 'body_hz'" in capsys.readouterr().err


def test_json_report(tmp_path, capsys):
    out = tmp_path / "j.wav"
    assert sfx_synth.main(["make", "drop", "--out", str(out), "--json", "--seed", "4"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["preset"] == "drop" and data["seed"] == 4 and data["file"] == str(out)
    assert data["params"]["sweep_ms"] == 700.0 and data["frames"] == round(1.2 * 44100)


def test_command_line_end_to_end(tmp_path):
    out = tmp_path / "cli.wav"
    done = subprocess.run([sys.executable, str(SCRIPT), "make", "tick", "--out", str(out)], capture_output=True, text=True)
    assert done.returncode == 0 and out.is_file() and "wrote" in done.stdout
    again = subprocess.run([sys.executable, str(SCRIPT), "make", "tick", "--out", str(out)], capture_output=True, text=True)
    assert again.returncode == 2 and "Traceback" not in again.stderr
    nothing = subprocess.run([sys.executable, str(SCRIPT)], capture_output=True, text=True)
    assert nothing.returncode == 2


def test_wav_header_fields(tmp_path):
    _, out = make(tmp_path, "tick")
    blob = out.read_bytes()
    riff, size, wave_tag = struct.unpack("<4sI4s", blob[:12])
    assert (riff, wave_tag) == (b"RIFF", b"WAVE") and size == len(blob) - 8
