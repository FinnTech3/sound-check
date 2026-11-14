# Agensi listing copy

Paste these into the submit form at agensi.io/dashboard/submit. Upload `dist/sound-check.zip`
(build it with `python3 tools/agensi_build.py agensi/sound-check`, which also checks this file against Agensi's field limits).
Logo and screenshots are in `agensi/media/`.

| Field | Value |
|---|---|
| Title | Sound Check: Give Your Agent Ears for Audio |
| Categories | Testing & Debugging; Image & Video; Productivity |
| Suggested price | $9 one-time |
| Tags | audio, wav, sound-effects, testing, video |
| Compatibility note | Requires Python 3.10+. WAV files only. No packages, no network access, no API key. |
| Permissions | Terminal (runs two Python scripts from temporary files). audio_probe.py reads the WAV you name and writes nothing. sfx_synth.py writes one WAV, only to the path you give it, and never overwrites a file unless you pass --force. No network access, no environment variables. |
| Docs link | https://github.com/FinnTech3/sound-check |

## Summary

Turns a WAV file into measurements an agent can reason about, including clipping, silence, onsets, tempo, spectrum, stereo phase and sync to cut times. Also makes simple sound effects from code and tunes them by measuring. Standard library Python, no installs.

## Description

Your agent can write code that renders a film, a demo or a game with sound. It cannot hear what it made. It cannot tell a clipped hit from a clean one, spot a sound landing 80 ms after the cut, or notice a silent gap in the middle.

This skill gives it evidence instead. Ask "is this audio clipping?" or "does the hit land on the cut at 1.20 s?" and the agent measures the file and answers with numbers: peak and clipping runs, silence before, after and inside the sound, onset times, attack and decay, a tempo estimate with a confidence figure, brightness and a five-band energy split, stereo correlation, and for each cut time the offset in milliseconds with a pass or fail against your tolerance.

It also writes sounds. Nine presets (click, tick, pop, thump, whoosh, riser, hit, chime, drop) are synthesised from code and are deterministic for a given seed. The loop is make, measure, change one parameter, measure again, until the numbers match the brief.

**How it works.** Two bundled Python scripts, standard library only. `audio_probe.py` reads a WAV (PCM 8, 16, 24 or 32-bit, or 32/64-bit float) and prints text or JSON. `sfx_synth.py` writes a WAV. The agent reads the numbers and explains them. A bounded cost keeps long files quick: at most 1200 seconds are read, and the spectrum uses at most 64 frames.

**What makes it different**

- Honest about limits: measurements are not hearing, and the skill says so. Loudness is a plain RMS estimate and is never called LUFS. Tempo and spectrum are labelled as estimates, and "not enough rhythm" is a valid answer.
- Evidence, not opinion: no model, so no "this sounds expensive". It can say a sound is 4 dB louder or 80 ms late.
- Safe by design: the probe only reads, the synthesiser writes only the one path you give it, and neither installs anything.

**Where it stops.** WAV only (convert other formats first). It cannot judge taste, quality or genre, and it finds clipping only where samples sit at full scale.

## See it in action

**Request:** "My demo cuts to the title card at 1.20 seconds. Check that hit_late.wav lands on it, 40 ms tolerance."

**What the agent ran:** `python3 "$PROBE" probe hit_late.wav --cuts 1.20 --tolerance-ms 40`

**Full output:**

```console
audio_probe: hit_late.wav
format    sample_rate 44100 | channels 1 | bit_depth 16 | sample_format int | duration_s 3.0 | analysed_s 3.0
level     peak_dbfs -6.0 | peak_time_s 1.2842 | rms_dbfs -29.22 | dc_offset 0.00024
loudness  active_rms_dbfs -22.91 | basis plain RMS, not LUFS (estimate)
clipping  runs 0 | longest_run 0 | full_scale_samples 0 | first_s None | over_full_scale False
silence   threshold_dbfs -60.0 | leading_s 1.2802 | trailing_s 0.9048 | active_s 0.818 | gaps_total 0 | gaps []
events    count 1 | onsets_s [1.2802] | attack_ms 4.0 | decay_ms 320.0
tempo     bpm None | confidence 0.0 | note not enough rhythm: 1 onsets in 3.0 s (needs 6+) (estimate)
spectrum  centroid_hz 1324.6 | band_percent bass 79.9 | low_mid 1.3 | mid 4.8 | high_mid 5.9 | high 8.1 | peakiness_log10 2.69 | frames_used 23 | sweep_hz None | strongest_hz 64.7 (estimate)
sync      tolerance_ms 40.0 | pass False | cuts [cut_s 1.2 | offset_ms 80.2 | pass False]
Sounds like (inferred from measurements, not heard): short transient, 320 ms decay, warm, tonal near 65 Hz
FINDING [sync] cut at 1.2 s: 80 ms late (tolerance 40 ms)
```

**Result:**

**Verdict: the sync check fails.** The sound starts 80 ms after the cut, outside the 40 ms tolerance.

| Measurement | Value |
|---|---|
| Cut | 1.20 s |
| First onset | 1.2802 s |
| Offset | +80.2 ms (positive is late) |
| Peak | -6.0 dBFS, no clipping |
| Decay | 320 ms |

The sound is silent until 1.2802 s (`silence.leading_s`), so this is a placement problem and not a quiet onset the check missed. "Sounds like", inferred from the measurements and not heard: a short transient with a 320 ms decay, warm, tonal near 65 Hz. The loudness figure and the spectrum are estimates.

**Next step:** start the sound 80 ms earlier, write it to a new file, and probe again. After the change (a new file, `hit.wav`, with the sound starting at 1200 ms) the same check reports:

```console
events    count 1 | onsets_s [1.2002] | attack_ms 4.0 | decay_ms 320.0
sync      tolerance_ms 40.0 | pass True | cuts [cut_s 1.2 | offset_ms 0.2 | pass True]
findings: none
```

Offset +0.2 ms, pass, no findings.

## Limitations

- WAV only. mp3, ogg, flac and m4a must be converted first, and the skill never installs a converter.
- Measurements are not hearing. There is no model in the scripts, so no judgement of taste, quality or genre.
- Loudness is a plain RMS estimate over gated 400 ms blocks. It is not LUFS.
- Tempo and spectrum are estimates. Tempo can be double or half the felt tempo, and returns "not enough rhythm" when there is no steady pulse.
- Clipping is found only where samples sit at full scale. Clipping that was turned down afterwards is not detected.
- An onset hidden under the tail of a louder sound may not register, which can make a sync check fail with "no onset within 500 ms".
- At most 1200 seconds of audio are read and at most 64 spectrum frames are used. Long files are sampled for the spectrum.
- The sound-effect presets are small synthesis recipes, not recordings.

## FAQ

**Can it hear my audio?** No. It measures samples and says what the numbers show. The one-line "sounds like" is inferred from measurements and is labelled that way.

**Is the loudness figure LUFS?** No. It is a plain RMS of gated 400 ms blocks with no frequency weighting, and the skill never calls it LUFS.

**Does it need ffmpeg or any package?** No. It uses only the Python standard library. If your file is not a WAV, the skill asks you to convert it with a tool you already have.

**Will it overwrite my file?** No. The probe only reads. The synthesiser writes only the path you give it, and refuses if a file is already there unless you pass --force.

**How long does a long file take?** 10 minutes of 44.1 kHz stereo took 5.6 seconds when I rechecked. The cost is bounded by a 1200 second cap.

**Which Python versions?** The tests pass on Python 3.10, 3.11, 3.12 and 3.13 on Linux.

**Which agents does it work with?** Any agent that supports SKILL.md and can run a Python script from a temporary file.

## Use cases

- Check a generated soundtrack for clipping, dropouts and silence
- Find out how many milliseconds late a sound lands against a cut
- Synthesise a UI click or whoosh and tune it by measuring it
