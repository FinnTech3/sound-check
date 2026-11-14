"""Onsets, tempo, decay, spectrum and the sync check, on signals with known timing and content."""

import re

import pytest

from conftest import RATE, clicks, decaying_sine, noise, silence, sine, write_wav


def test_onsets_land_within_two_ms_of_the_truth(tmp_path, probe):
    times = [0.30, 0.81, 1.27, 2.05, 2.46]
    code, r, _ = probe(write_wav(tmp_path / "t.wav", [clicks(times, 3.0)]))
    got = r["events"]["onsets_s"]
    assert r["events"]["count"] == len(times)
    for want, have in zip(times, got):
        assert have == pytest.approx(want, abs=0.002)


def test_onset_at_the_very_start_is_found(tmp_path, probe):
    r = probe(write_wav(tmp_path / "s.wav", [clicks([0.0, 0.5], 1.0)]))[1]
    assert r["events"]["onsets_s"][0] == pytest.approx(0.0, abs=0.002) and r["events"]["count"] == 2


def test_quiet_hit_among_loud_ones_is_still_an_onset(tmp_path, probe):
    x = [a + b for a, b in zip(clicks([0.5, 1.5], 2.5, amp=0.9), clicks([1.0], 2.5, amp=0.06))]
    r = probe(write_wav(tmp_path / "q.wav", [x]))[1]
    assert r["events"]["count"] == 3 and r["events"]["onsets_s"][1] == pytest.approx(1.0, abs=0.002)


def test_steady_noise_has_no_onsets(tmp_path, probe):
    r = probe(write_wav(tmp_path / "n.wav", [noise(3.0)]))[1]
    assert r["events"]["count"] <= 1  # at most the start of the file


@pytest.mark.parametrize("bpm", [90, 120, 150])
def test_tempo_of_a_click_track(tmp_path, probe, bpm):
    step = 60 / bpm
    r = probe(write_wav(tmp_path / "bpm.wav", [clicks([0.4 + i * step for i in range(16)], 0.4 + 16 * step)]))[1]
    assert r["tempo"]["bpm"] == pytest.approx(bpm, abs=bpm * 0.015)
    assert r["tempo"]["confidence"] >= 0.8 and "tempo" in r["estimates"]


def test_tempo_survives_a_little_timing_jitter(tmp_path, probe):
    jitter = [0.006, -0.008, 0.004, -0.005, 0.009, -0.003, 0.007, -0.006, 0.002, -0.009, 0.005, -0.004]
    times = [0.4 + 0.5 * i + jitter[i] for i in range(12)]
    r = probe(write_wav(tmp_path / "j.wav", [clicks(times, 7.0)]))[1]
    assert r["tempo"]["bpm"] == pytest.approx(120, abs=2)


def test_one_click_is_not_enough_rhythm(tmp_path, probe):
    r = probe(write_wav(tmp_path / "one.wav", [clicks([0.5], 4.0)]))[1]
    assert r["tempo"]["bpm"] is None and "not enough rhythm" in r["tempo"]["note"]


def test_irregular_clicks_are_not_a_tempo(tmp_path, probe):
    times, t = [], 0.3
    for gap in [0.31, 0.77, 0.43, 1.12, 0.27, 0.95, 0.52, 0.68, 0.36, 1.05, 0.44, 0.83, 0.29, 0.99]:
        times.append(t)
        t += gap
    r = probe(write_wav(tmp_path / "irr.wav", [clicks(times, t + 0.5)]))[1]
    assert r["events"]["count"] >= 12
    assert r["tempo"]["bpm"] is None and "not enough rhythm" in r["tempo"]["note"]


def test_a_sustained_tone_has_no_tempo(tmp_path, probe):
    r = probe(write_wav(tmp_path / "tone.wav", [sine(440, 5.0)]))[1]
    assert r["tempo"]["bpm"] is None and "not enough rhythm" in r["tempo"]["note"]


@pytest.mark.parametrize("decay_ms", [150, 400, 900])
def test_decay_time_matches_the_envelope(tmp_path, probe, decay_ms):
    r = probe(write_wav(tmp_path / "d.wav", [decaying_sine(500, decay_ms, 2.5)]))[1]
    assert r["events"]["decay_ms"] == pytest.approx(decay_ms, abs=30)
    assert r["events"]["attack_ms"] < 5
    assert "decay" in r["summary"]


def test_a_swell_reports_a_long_attack(tmp_path, probe):
    n = round(2.0 * RATE)
    x = [(i / n) ** 2 * 0.8 * s for i, s in enumerate(sine(600, 2.0, amp=1.0))]
    r = probe(write_wav(tmp_path / "swell.wav", [x]))[1]
    assert r["events"]["attack_ms"] > 1500 and r["summary"].startswith("swell building")


def test_sync_passes_when_the_hit_is_on_the_cut(tmp_path, probe):
    code, r, _ = probe(write_wav(tmp_path / "ok.wav", [clicks([1.0, 2.0], 3.0)]), "--cuts", "1.0,2.0")
    assert code == 0 and r["sync"]["pass"] is True
    assert all(abs(c["offset_ms"]) <= 2 and c["pass"] for c in r["sync"]["cuts"])


def test_sync_catches_a_late_hit(tmp_path, probe):
    code, r, _ = probe(write_wav(tmp_path / "late.wav", [clicks([1.0, 2.08], 3.0)]), "--cuts", "1.0,2.0")
    assert code == 1 and r["sync"]["pass"] is False
    first, second = r["sync"]["cuts"]
    assert first["pass"] and second["offset_ms"] == pytest.approx(80, abs=3) and not second["pass"]
    assert any(f["kind"] == "sync" and "80 ms late" in f["message"] for f in r["findings"])


def test_sync_reports_an_early_hit_with_a_negative_offset(tmp_path, probe):
    code, r, _ = probe(write_wav(tmp_path / "early.wav", [clicks([0.94], 2.0)]), "--cuts", "1.0")
    assert code == 1 and r["sync"]["cuts"][0]["offset_ms"] == pytest.approx(-60, abs=3)
    assert "early" in r["findings"][0]["message"]


def test_sync_tolerance_is_adjustable(tmp_path, probe):
    path = write_wav(tmp_path / "tol.wav", [clicks([1.06], 2.0)])
    assert probe(path, "--cuts", "1.0")[0] == 1
    assert probe(path, "--cuts", "1.0", "--tolerance-ms", "80")[0] == 0


def test_sync_with_no_onset_near_the_cut_fails(tmp_path, probe):
    code, r, _ = probe(write_wav(tmp_path / "far.wav", [clicks([0.2], 4.0)]), "--cuts", "3.0")
    assert code == 1 and r["sync"]["cuts"][0]["offset_ms"] is None
    assert "no onset within 500 ms" in r["findings"][0]["message"]


def test_spectrum_of_a_sine_is_where_it_should_be(tmp_path, probe):
    r = probe(write_wav(tmp_path / "k.wav", [sine(1000, 1.0)]))[1]
    sp = r["spectrum"]
    assert sp["centroid_hz"] == pytest.approx(1000, abs=20) and sp["strongest_hz"] == pytest.approx(1000, abs=10)
    assert sp["band_percent"]["mid"] > 98 and sp["peakiness_log10"] > 2.2 and sp["sweep_hz"] is None
    assert re.search(r"tonal near (99\d|100\d) Hz", r["summary"]) and "spectrum" in r["estimates"]


def test_spectrum_bands_follow_the_pitch(tmp_path, probe):
    low = probe(write_wav(tmp_path / "lo.wav", [sine(80, 1.0)]))[1]["spectrum"]["band_percent"]
    high = probe(write_wav(tmp_path / "hi.wav", [sine(9000, 1.0)]))[1]["spectrum"]["band_percent"]
    assert low["bass"] > 98 and high["high"] > 98 and sum(low.values()) == pytest.approx(100, abs=0.5)


def test_white_noise_reads_as_noise_like_and_bright(tmp_path, probe):
    r = probe(write_wav(tmp_path / "wn.wav", [noise(2.0)]))[1]
    assert "noise-like" in r["summary"] and r["spectrum"]["centroid_hz"] > 6000


def test_a_sweep_is_reported_as_a_sweep(tmp_path, probe):
    import math

    n, ph, x = round(2.0 * RATE), 0.0, []
    for i in range(n):
        x.append(0.5 * math.sin(ph))
        ph += 2 * math.pi * (300 + 2700 * i / n) / RATE
    r = probe(write_wav(tmp_path / "sw.wav", [x]))[1]
    lo, hi = r["spectrum"]["sweep_hz"]
    assert lo < 1200 < hi and "sweeping" in r["summary"]


def test_spectrum_cost_is_capped_on_a_long_file(tmp_path, probe):
    r = probe(write_wav(tmp_path / "long.wav", [sine(440, 90.0, rate=8000)], rate=8000))[1]
    assert r["spectrum"]["frames_used"] <= 64 and r["spectrum"]["centroid_hz"] == pytest.approx(440, abs=15)


def test_summary_is_labelled_as_inference(tmp_path, probe):
    _, text, _ = probe(write_wav(tmp_path / "t.wav", [sine(440, 0.5)]), text=True)
    assert "Sounds like (inferred from measurements, not heard):" in text and "(estimate)" in text
    assert "audio_probe:" in text and text.rstrip().endswith("findings: none")


def test_a_short_click_file_is_described_as_a_click(tmp_path, probe):
    r = probe(write_wav(tmp_path / "c.wav", [silence(0.05) + clicks([0.0], 0.1, amp=0.8) + silence(0.2)]))[1]
    assert r["summary"].startswith("very short click")


def test_tempo_of_a_beat_made_with_the_synth(tmp_path, probe):
    """A kick / hat / snare pattern from sfx_synth presets at 120 BPM: the whole chain, synth to probe."""
    import sfx_synth

    def hit(name, **params):
        q, _ = sfx_synth.render(name, params, 1, sfx_synth.PRESETS[name][1], RATE)
        return [v / 32768 for v in q]

    kick, hat, snare = hit("thump"), hit("click", level_db=-14), hit("hit", level_db=-8)
    step, x = 0.5, [0.0] * round(10.0 * RATE)
    for bar in range(4):
        for sub, snd in ((0, kick), (0.5, hat), (1, snare), (1.5, hat), (2, kick), (2.5, hat), (3, snare), (3.5, hat)):
            i = round((bar * 4 + sub) * step * RATE)
            for k, v in enumerate(snd):
                x[i + k] += v if i + k < len(x) else 0.0
    peak = max(abs(v) for v in x)
    r = probe(write_wav(tmp_path / "beat.wav", [[0.8 * v / peak for v in x]]))[1]
    assert r["tempo"]["bpm"] == pytest.approx(120, abs=2) and "BPM" in r["summary"]
