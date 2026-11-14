"""Levels, formats, clipping, silence and stereo, measured on synthetic files with known answers."""

import math

import pytest

import audio_probe
from conftest import RATE, clicks, noise, silence, sine, write_wav


def test_sine_level_numbers(tmp_path, probe):
    path = write_wav(tmp_path / "s.wav", [sine(440, 1.0, amp=0.5)])
    code, r, _ = probe(path)
    assert code == 0 and r["findings"] == []
    assert r["format"] == {"sample_rate": RATE, "channels": 1, "bit_depth": 16, "sample_format": "int",
                           "duration_s": 1.0, "analysed_s": 1.0}
    assert r["level"]["peak_dbfs"] == pytest.approx(-6.02, abs=0.02)
    assert r["level"]["rms_dbfs"] == pytest.approx(-9.03, abs=0.05)
    assert abs(r["level"]["dc_offset"]) < 0.001


@pytest.mark.parametrize(("bits", "kind", "tol"), [(8, "int", 0.15), (16, "int", 0.02), (24, "int", 0.02),
                                                    (32, "int", 0.02), (32, "float", 0.02), (64, "float", 0.02)])
def test_every_supported_format_reads_the_same_sine(tmp_path, probe, bits, kind, tol):
    path = write_wav(tmp_path / "f.wav", [sine(1000, 0.5, amp=0.25)], bits=bits, kind=kind)
    code, r, _ = probe(path)
    assert code == 0
    assert r["format"]["bit_depth"] == bits and r["format"]["sample_format"] == kind
    assert r["level"]["peak_dbfs"] == pytest.approx(-12.04, abs=tol + 0.05)
    assert r["level"]["rms_dbfs"] == pytest.approx(-15.05, abs=tol + 0.1)


def test_extensible_header_is_accepted(tmp_path, probe):
    path = write_wav(tmp_path / "x.wav", [sine(500, 0.3)], bits=24, extensible=True)
    code, r, _ = probe(path)
    assert code == 0 and r["format"]["bit_depth"] == 24
    assert r["level"]["peak_dbfs"] == pytest.approx(-6.02, abs=0.05)


def test_negative_24_bit_samples_keep_their_sign(tmp_path, probe):
    path = write_wav(tmp_path / "neg.wav", [[-0.5] * 4410], bits=24)
    code, r, _ = probe(path)
    assert r["level"]["peak_dbfs"] == pytest.approx(-6.02, abs=0.05)
    assert r["level"]["dc_offset"] == pytest.approx(0.5, abs=0.001)  # reported as a magnitude
    assert code == 1 and [f["kind"] for f in r["findings"]] == ["dc_offset"]


def test_silent_file_is_a_finding(tmp_path, probe):
    code, r, _ = probe(write_wav(tmp_path / "z.wav", [silence(1.0)]))
    assert code == 1 and [f["kind"] for f in r["findings"]] == ["silent"]
    assert r["level"]["peak_dbfs"] == -120.0 and r["summary"] == "silent"


def test_eight_bit_silence_is_centred_not_loud(tmp_path, probe):
    code, r, _ = probe(write_wav(tmp_path / "z8.wav", [silence(0.5)], bits=8))
    assert r["level"]["peak_dbfs"] == -120.0 and r["level"]["dc_offset"] == 0.0


def test_clipped_square_wave_is_found(tmp_path, probe):
    square = [1.0 if (i // 50) % 2 == 0 else -1.0 for i in range(RATE // 2)]
    code, r, _ = probe(write_wav(tmp_path / "sq.wav", [square]))
    assert code == 1
    c = r["clipping"]
    assert c["runs"] >= 400 and c["longest_run"] >= 49 and c["first_s"] < 0.001
    assert c["full_scale_samples"] > RATE // 4 and r["level"]["peak_dbfs"] > -0.01
    assert "clipped" in r["summary"] and any(f["kind"] == "clipping" for f in r["findings"])


def test_one_full_scale_sample_is_a_peak_not_clipping(tmp_path, probe):
    x = sine(300, 0.5, amp=0.3)
    x[1000] = 1.0
    code, r, _ = probe(write_wav(tmp_path / "peak.wav", [x]))
    assert code == 0 and r["clipping"]["runs"] == 0 and r["clipping"]["full_scale_samples"] == 1


def test_a_run_that_crosses_block_boundaries_counts_once(tmp_path, probe):
    x = sine(100, 3.0, amp=0.1)
    for i in range(100_000, 100_900):  # 900 samples, far longer than one 5 ms block and across a 1 s block edge
        x[i] = 1.0
    code, r, _ = probe(write_wav(tmp_path / "long.wav", [x]))
    assert r["clipping"]["runs"] == 1 and r["clipping"]["longest_run"] == 900
    assert r["clipping"]["first_s"] == pytest.approx(100_000 / RATE, abs=1e-4)


def test_float_file_over_full_scale_is_flagged(tmp_path, probe):
    code, r, _ = probe(write_wav(tmp_path / "hot.wav", [sine(200, 0.3, amp=1.8)], bits=32, kind="float"))
    assert code == 1 and r["clipping"]["over_full_scale"] and r["level"]["peak_dbfs"] == pytest.approx(5.1, abs=0.1)


def test_dc_offset_is_flagged(tmp_path, probe):
    x = [0.2 + 0.1 * math.sin(2 * math.pi * 300 * i / RATE) for i in range(RATE // 2)]
    code, r, _ = probe(write_wav(tmp_path / "dc.wav", [x]))
    assert code == 1 and r["level"]["dc_offset"] == pytest.approx(0.2, abs=0.002)
    assert [f["kind"] for f in r["findings"]] == ["dc_offset"]


def test_leading_trailing_silence_and_gap(tmp_path, probe):
    x = silence(0.123) + sine(500, 0.4) + silence(0.6) + sine(500, 0.3) + silence(0.2)
    code, r, _ = probe(write_wav(tmp_path / "gaps.wav", [x]))
    s = r["silence"]
    assert s["leading_s"] == pytest.approx(0.123, abs=0.006)
    assert s["trailing_s"] == pytest.approx(0.2, abs=0.006)
    assert s["gaps_total"] == 1
    assert s["gaps"][0][0] == pytest.approx(0.523, abs=0.01) and s["gaps"][0][1] == pytest.approx(1.123, abs=0.01)
    assert any("silent gap" in n for n in r["notes"])


def test_short_silence_is_not_listed_as_a_gap(tmp_path, probe):
    x = sine(500, 0.4) + silence(0.1) + sine(500, 0.4)
    assert probe(write_wav(tmp_path / "short.wav", [x]))[1]["silence"]["gaps_total"] == 0


def test_stereo_out_of_phase_is_a_finding(tmp_path, probe):
    left = sine(300, 0.5)
    code, r, _ = probe(write_wav(tmp_path / "oop.wav", [left, [-v for v in left]]))
    assert code == 1
    assert r["stereo"]["correlation"] == pytest.approx(-1.0, abs=0.001) and r["stereo"]["mono_change_db"] < -60
    assert [f["kind"] for f in r["findings"]] == ["mono_compat"]


def test_stereo_identical_channels_are_clean(tmp_path, probe):
    left = sine(300, 0.5)
    code, r, _ = probe(write_wav(tmp_path / "dual.wav", [left, list(left)]))
    assert code == 0 and r["stereo"]["correlation"] == pytest.approx(1.0, abs=0.001)
    assert r["stereo"]["mono_change_db"] == pytest.approx(0.0, abs=0.05)


def test_stereo_independent_noise_loses_three_db_in_mono(tmp_path, probe):
    code, r, _ = probe(write_wav(tmp_path / "wide.wav", [noise(1.0, seed=1), noise(1.0, seed=2)]))
    assert code == 0 and abs(r["stereo"]["correlation"]) < 0.05
    assert r["stereo"]["mono_change_db"] == pytest.approx(-3.0, abs=0.3)


def test_mono_file_has_no_stereo_block(tmp_path, probe):
    assert probe(write_wav(tmp_path / "m.wav", [sine(300, 0.2)]))[1]["stereo"] is None


def test_loudness_is_labelled_as_plain_rms_not_lufs(tmp_path, probe):
    code, r, _ = probe(write_wav(tmp_path / "l.wav", [silence(1.0) + sine(1000, 1.0, amp=0.5) + silence(1.0)]))
    assert "not LUFS" in r["loudness"]["basis"] and "loudness" in r["estimates"]
    assert r["loudness"]["active_rms_dbfs"] == pytest.approx(-9.03, abs=1.5)  # the silence is gated out
    assert r["level"]["rms_dbfs"] == pytest.approx(-13.8, abs=0.1)  # the plain whole-file RMS keeps it


def test_pure_python_dot_fallback_gives_the_same_numbers(tmp_path, probe, monkeypatch):
    path = write_wav(tmp_path / "d.wav", [sine(700, 0.5), sine(900, 0.5)])
    reference = probe(path)[1]
    monkeypatch.setattr(audio_probe, "dot", lambda a, b: sum(x * y for x, y in zip(a, b)))
    assert probe(path)[1] == reference


def test_probe_never_writes(tmp_path, probe):
    path = write_wav(tmp_path / "ro.wav", [clicks([0.2, 0.7], 1.2)])
    before, stamp = path.read_bytes(), path.stat().st_mtime_ns
    probe(path)
    assert path.read_bytes() == before and path.stat().st_mtime_ns == stamp
    assert [p.name for p in tmp_path.iterdir()] == ["ro.wav"]
