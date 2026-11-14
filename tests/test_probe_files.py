"""Bad, damaged, odd and oversized files, and the command line. Exit 2 is a user mistake, 1 is a finding."""

import json
import os
import struct
import subprocess
import sys
from pathlib import Path

import pytest

import audio_probe
from conftest import RATE, clicks, sine, write_wav

SCRIPT = Path(audio_probe.__file__)


def test_a_text_file_is_not_a_wav(tmp_path, probe):
    path = tmp_path / "notes.wav"
    path.write_text("this is not audio, it is a sentence of text that is long enough to matter")
    code, out, err = probe(path)
    assert code == 2 and out is None and "not a RIFF/WAVE file" in err and "Convert" in err


def test_random_bytes_do_not_crash(tmp_path, probe):
    path = tmp_path / "junk.wav"
    path.write_bytes(bytes((i * 37 + 11) % 256 for i in range(5000)))
    code, _, err = probe(path)
    assert code == 2 and err.startswith("error:")


def test_a_riff_header_with_the_wrong_form_type_is_rejected(tmp_path, probe):
    path = tmp_path / "avi.wav"
    path.write_bytes(b"RIFF" + struct.pack("<I", 100) + b"AVI " + b"\x00" * 100)
    assert probe(path)[0] == 2


def test_empty_file_and_tiny_files(tmp_path, probe):
    for size in (0, 3, 11, 12, 20):
        path = tmp_path / f"t{size}.wav"
        path.write_bytes(b"RIFF\x00\x00\x00\x00WAVEfmt "[:size])
        code, _, err = probe(path)
        assert code == 2 and err.startswith("error:"), size


def test_zero_length_audio_is_rejected(tmp_path, probe):
    path = tmp_path / "empty.wav"
    fmt = struct.pack("<HHIIHH", 1, 1, 44100, 88200, 2, 16)
    path.write_bytes(b"RIFF" + struct.pack("<I", 36) + b"WAVEfmt " + struct.pack("<I", 16) + fmt + b"data" + struct.pack("<I", 0))
    code, _, err = probe(path)
    assert code == 2 and "no audio frames" in err


def test_header_only_file_has_no_data_chunk(tmp_path, probe):
    full = write_wav(tmp_path / "full.wav", [sine(300, 0.1)]).read_bytes()
    path = tmp_path / "head.wav"
    path.write_bytes(full[:36])
    code, _, err = probe(path)
    assert code == 2 and "no data chunk" in err


def test_data_chunk_before_fmt_is_rejected(tmp_path, probe):
    path = tmp_path / "order.wav"
    path.write_bytes(b"RIFF" + struct.pack("<I", 40) + b"WAVE" + b"data" + struct.pack("<I", 4) + b"\x00" * 4
                     + b"fmt " + struct.pack("<IHHIIHH", 16, 1, 1, 8000, 16000, 2, 16))
    code, _, err = probe(path)
    assert code == 2 and "fmt" in err


def test_compressed_formats_are_refused_with_advice(tmp_path, probe):
    path = tmp_path / "mp3.wav"
    fmt = struct.pack("<HHIIHH", 0x55, 2, 44100, 16000, 1, 0)
    path.write_bytes(b"RIFF" + struct.pack("<I", 4 + 8 + 16 + 8 + 16) + b"WAVEfmt " + struct.pack("<I", 16) + fmt
                     + b"data" + struct.pack("<I", 16) + b"\x00" * 16)
    code, _, err = probe(path)
    assert code == 2 and "Convert to PCM WAV" in err


def test_odd_bit_depth_and_inconsistent_alignment(tmp_path, probe):
    for bits, align, ch in ((12, 2, 1), (16, 3, 1), (16, 2, 0), (16, 2, 9)):
        path = tmp_path / f"b{bits}{align}{ch}.wav"
        fmt = struct.pack("<HHIIHH", 1, ch, 44100, 88200, align, bits)
        path.write_bytes(b"RIFF" + struct.pack("<I", 36 + 8) + b"WAVEfmt " + struct.pack("<I", 16) + fmt
                         + b"data" + struct.pack("<I", 8) + b"\x01" * 8)
        assert probe(path)[0] == 2, (bits, align, ch)


def test_a_cut_fmt_chunk_is_reported(tmp_path, probe):
    path = tmp_path / "cutfmt.wav"
    path.write_bytes(b"RIFF" + struct.pack("<I", 20) + b"WAVEfmt " + struct.pack("<I", 8) + b"\x01\x00\x01\x00\x44\xac\x00\x00")
    code, _, err = probe(path)
    assert code == 2 and "cut short" in err


def test_truncated_data_is_analysed_and_reported(tmp_path, probe):
    path = write_wav(tmp_path / "cut.wav", [sine(440, 1.0)], cut=40000)
    code, r, _ = probe(path)
    assert code == 1 and [f["kind"] for f in r["findings"]] == ["truncated"]
    assert 0.5 < r["format"]["duration_s"] < 0.6 and r["level"]["peak_dbfs"] == pytest.approx(-6.02, abs=0.05)


def test_a_header_that_claims_gigabytes_does_not_hang(tmp_path, probe):
    path = write_wav(tmp_path / "huge.wav", [sine(440, 0.5)], data_size=3_000_000_000)
    code, r, _ = probe(path)
    assert code == 1 and r["format"]["duration_s"] == pytest.approx(0.5, abs=0.001)
    assert r["findings"][0]["kind"] == "truncated"


def test_streaming_style_header_is_not_called_truncated(tmp_path, probe):
    path = write_wav(tmp_path / "stream.wav", [sine(440, 0.5)], data_size=0xFFFFFFFF)
    code, r, _ = probe(path)
    assert code == 0 and r["format"]["duration_s"] == pytest.approx(0.5, abs=0.001)


def test_a_half_frame_at_the_end_is_dropped_and_reported(tmp_path, probe):
    path = write_wav(tmp_path / "odd.wav", [sine(440, 0.5)], cut=1, data_size=None)
    code, r, _ = probe(path)
    assert code == 1 and r["findings"][0]["kind"] == "truncated"


def test_chunks_after_the_data_are_ignored(tmp_path, probe):
    path = write_wav(tmp_path / "tail.wav", [sine(440, 0.3)])
    path.write_bytes(path.read_bytes() + b"LIST" + struct.pack("<I", 5) + b"abcde" + b"\x00")
    code, r, _ = probe(path)
    assert code == 0 and r["format"]["duration_s"] == pytest.approx(0.3, abs=0.001)


def test_nan_in_a_float_file_is_refused(tmp_path, probe):
    x = sine(440, 0.3)
    x[100] = float("nan")
    code, _, err = probe(write_wav(tmp_path / "nan.wav", [x], bits=32, kind="float"))
    assert code == 2 and "NaN" in err


def test_missing_file_and_directory(tmp_path, probe):
    assert probe(tmp_path / "nope.wav")[0] == 2
    code, _, err = probe(tmp_path)
    assert code == 2 and "not a regular file" in err


@pytest.mark.parametrize("args", [["--cuts", "abc"], ["--cuts", "1.0,x"], ["--cuts", "-1"], ["--tolerance-ms", "-5"],
                                  ["--max-seconds", "0"]])
def test_bad_options_are_a_usage_error(tmp_path, probe, args):
    code, _, err = probe(write_wav(tmp_path / "a.wav", [sine(440, 0.2)]), *args)
    assert code == 2 and err.startswith("error:")


def test_argparse_errors_exit_2(tmp_path):
    with pytest.raises(SystemExit) as e:
        audio_probe.main(["probe"])
    assert e.value.code == 2
    with pytest.raises(SystemExit) as e:
        audio_probe.main([])
    assert e.value.code == 2


def test_analysis_cap_reads_only_the_first_seconds(tmp_path, probe):
    path = write_wav(tmp_path / "six.wav", [clicks([0.5, 1.0, 5.0], 6.0)])
    code, r, _ = probe(path, "--max-seconds", "2")
    assert r["format"]["duration_s"] == 6.0 and r["format"]["analysed_s"] == 2.0
    assert r["events"]["count"] == 2 and any("capped" in n for n in r["notes"])


def test_the_default_cap_is_applied_to_huge_files(tmp_path, probe, monkeypatch):
    monkeypatch.setattr(audio_probe, "MAX_SECONDS", 3)
    path = write_wav(tmp_path / "ten.wav", [sine(300, 10.0, rate=8000)], rate=8000)
    import argparse

    parsed = argparse.Namespace(max_seconds=audio_probe.MAX_SECONDS, silence_db=-60.0, cuts=[], tolerance_ms=40.0)
    res = audio_probe.analyse(str(path), parsed)
    assert res["format"]["analysed_s"] == 3.0 and res["format"]["duration_s"] == 10.0


def test_a_ten_minute_stereo_file_finishes_in_seconds(tmp_path):
    """Whole-file cost on a long file: 10 minutes of 8 kHz stereo (the cost scales with samples, not minutes)."""
    import time

    block = [sine(220, 1.0, rate=8000)] * 2
    chans = [c * 600 for c in block]
    path = write_wav(tmp_path / "ten.wav", chans, rate=8000)
    start = time.time()
    code = audio_probe.main(["probe", str(path), "--json"])
    assert code == 0 and time.time() - start < 20


def test_command_line_end_to_end(tmp_path):
    path = write_wav(tmp_path / "cli.wav", [clicks([0.5], 1.0)])
    done = subprocess.run([sys.executable, str(SCRIPT), "probe", str(path), "--json"], capture_output=True, text=True)
    assert done.returncode == 0 and json.loads(done.stdout)["events"]["count"] == 1
    done = subprocess.run([sys.executable, str(SCRIPT), "probe", str(tmp_path / "gone.wav")], capture_output=True, text=True)
    assert done.returncode == 2 and "Traceback" not in done.stderr and done.stdout == ""


def test_stereo_with_a_silent_channel_does_not_divide_by_zero(tmp_path, probe):
    code, r, _ = probe(write_wav(tmp_path / "half.wav", [sine(300, 0.3), [0.0] * round(0.3 * RATE)]))
    assert code == 0 and r["stereo"] is None


def test_many_channels_are_measured(tmp_path, probe):
    chans = [sine(200 * (i + 1), 0.3) for i in range(6)]
    code, r, _ = probe(write_wav(tmp_path / "six.wav", chans))
    assert code == 0 and r["format"]["channels"] == 6 and r["stereo"] is None


def test_tiny_files_are_measured_not_crashed_on(tmp_path, probe):
    for frames in (1, 2, 10, 100):
        path = write_wav(tmp_path / f"f{frames}.wav", [[0.5] * frames])
        code, r, _ = probe(path)
        assert code in (0, 1) and r["format"]["duration_s"] == pytest.approx(frames / RATE, abs=1e-3), frames


def test_fuzzed_files_never_traceback(tmp_path, capsys):
    """Flip header bytes, cut files short and scribble on the data: every outcome is exit 0, 1 or 2."""
    import random

    rng = random.Random(5)
    samples = [write_wav(tmp_path / "a.wav", [clicks([0.1, 0.3], 0.5)]),
               write_wav(tmp_path / "b.wav", [sine(300, 0.3), sine(500, 0.3)], bits=24),
               write_wav(tmp_path / "c.wav", [sine(300, 0.3)], bits=32, kind="float"),
               write_wav(tmp_path / "d.wav", [sine(300, 0.3)], bits=8, extensible=True)]
    target = tmp_path / "mut.wav"
    for i in range(150):
        blob = bytearray(samples[i % 4].read_bytes())
        if i % 3 == 0:
            for _ in range(rng.randint(1, 4)):
                blob[rng.randrange(80)] = rng.randrange(256)
        elif i % 3 == 1:
            blob = blob[: rng.randrange(len(blob))]
        else:
            for _ in range(20):
                blob[rng.randrange(len(blob))] = rng.randrange(256)
        target.write_bytes(bytes(blob))
        assert audio_probe.main(["probe", str(target), "--cuts", "0.2"]) in (0, 1, 2), i
        assert "Traceback" not in capsys.readouterr().err


@pytest.mark.parametrize(
    "args",
    [["--cuts", "nan"], ["--cuts", "inf"], ["--cuts", "1e999"], ["--tolerance-ms", "nan"], ["--tolerance-ms", "inf"],
     ["--silence-db", "nan"], ["--silence-db", "10"], ["--max-seconds", "nan"], ["--max-seconds", "inf"],
     ["--cuts", ",".join(["1"] * 201)]],
)  # fmt: skip
def test_non_finite_or_out_of_range_options_are_a_usage_error_not_a_traceback(tmp_path, probe, args):
    code, out, err = probe(write_wav(tmp_path / "a.wav", [sine(440, 0.2)]), *args)
    assert code == 2 and err.startswith("error:") and "Traceback" not in err and not out


def test_200_cuts_and_zero_dbfs_are_still_allowed(tmp_path, probe):
    path = write_wav(tmp_path / "a.wav", [sine(440, 0.2)])
    assert probe(path, "--cuts", ",".join(["0.1"] * 200), "--silence-db", "0")[0] in (0, 1)


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="named pipes need a POSIX system")
def test_a_pipe_is_refused_instead_of_blocking(tmp_path, probe):
    fifo = tmp_path / "pipe.wav"
    os.mkfifo(fifo)
    code, _, err = probe(fifo)
    assert code == 2 and "not a regular file" in err


def test_a_console_that_cannot_show_the_file_name_does_not_crash(tmp_path):
    """Windows consoles often use cp1252. A file name with a star or CJK characters must not end the run with a traceback."""
    path = write_wav(tmp_path / "日本★.wav", [sine(440, 0.2)])
    env = {**os.environ, "PYTHONIOENCODING": "cp1252", "PYTHONUTF8": "0"}
    script = Path(audio_probe.__file__)
    r = subprocess.run([sys.executable, str(script), "probe", str(path)], capture_output=True, env=env, timeout=60)
    assert r.returncode in (0, 1), r.stderr.decode(errors="replace")
    assert b"Traceback" not in r.stderr
