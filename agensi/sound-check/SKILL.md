---
name: sound-check
description: >
  Measures a WAV file for what an agent cannot hear: peak and clipping, silence and dropouts, onset times, tempo, brightness and stereo phase, and checks whether a sound lands on a cut time within a tolerance. Also writes simple sound effects from code (click, tick, pop, thump, whoosh, riser, hit, chime, drop) so they can be tuned by measuring. Use when the user asks "is this audio clipping", "does the hit land on the cut", "check the sound in my demo", "why is there silence in the middle", "make a click sound for this button". Do not use for music or speech generation, transcription, judging whether audio sounds good, converting formats or editing audio.
summary: Turns a WAV file into measurements an agent can reason about, including clipping, silence, onsets, tempo, spectrum, stereo phase and sync to cut times. Also makes simple sound effects from code and tunes them by measuring. Standard library Python, no installs.
version: 1.0.0
tags: [audio, wav, sound-effects, testing, video]
keywords: [audio analysis, clipping detection, audio sync, sound effects, silence detection, tempo, wav, spectrum]
use_cases:
  - Check a generated soundtrack for clipping, dropouts and silence
  - Find out how many milliseconds late a sound lands against a cut
  - Synthesise a UI click or whoosh and tune it by measuring it
docs_url: https://github.com/FinnTech3/sound-check
---

# Sound Check

You cannot hear. This skill gives you evidence instead: two scripts that turn a WAV file into numbers, and make simple sounds from code so you can improve them by measuring. `audio_probe.py` measures. `sfx_synth.py` makes. Everything you say about audio must trace back to a number one of them printed.

Requires: Python 3.10 or newer. Nothing to install, no network, no API key. WAV files only (PCM 8, 16, 24 or 32-bit, or 32/64-bit float). For mp3, ogg, flac or m4a, ask the user to convert the file to WAV first, or offer to do it with a converter they already have. Write the converted copy to a temporary folder, never over the original. Never install anything.

## Running the scripts

The scripts `scripts/audio_probe.py` and `scripts/sfx_synth.py` are delivered with this skill as text. Load each one with `get_skill` using that file path, write it **unchanged** to a temporary file (for example in the system temp folder), run it with `python3`, and delete the files when you are done. Never save them into the project or a skills folder, and never retype, shorten or edit them. If the skill folder is already on disk, run them from there. Below, `$PROBE` and `$SYNTH` stand for the paths you ran them from.

- `audio_probe.py` reads the file you name and writes nothing. It makes no network calls, reads no environment variables and does not change the file.
- `sfx_synth.py` writes one WAV file, only to the `--out` path you give it. It refuses to overwrite a file that already exists unless you pass `--force`, and it never creates folders. No network, no environment variables.

## Workflow: measuring a file

1. **Get the inputs.** You need the WAV path. For a sync check you also need the cut times in seconds (a frame number divided by the frame rate). Ask if you do not have them. Never guess a cut time.
2. **Probe first.** Before you say anything about the audio:

   ```sh
   python3 "$PROBE" probe FILE.wav --json
   python3 "$PROBE" probe FILE.wav --json --cuts 1.20,3.40 --tolerance-ms 40
   ```

   Exit code 0 means no findings, 1 means findings, 2 means the file or the options were bad. Use `--silence-db -50` for a noisy recording, `--max-seconds N` to read less than the default 1200 s.
3. **Read `findings` first.** Each has a `kind` (`clipping`, `dc_offset`, `silent`, `truncated`, `mono_compat`, `sync`) and a message. Then read the numbers that matter for the question. `references/measurements.md` says what every field means and where it stops being reliable.
4. **Report** in the format under Output. Say which numbers are estimates.
5. **If the user wants a fix,** write the result to a new file and probe that file again. Never overwrite the original. Quote the new numbers, not what you expect them to be.

## Workflow: making and tuning a sound

1. Turn the brief into numbers before you make anything: peak, decay, brightness, length, where it must land. If the user gave no numbers, propose some from `references/rules-of-thumb.md` and say they are rules of thumb.
2. `python3 "$SYNTH" list` shows the nine presets and their parameters. `references/presets.md` says which parameter moves which measurement.
3. Make it, then probe it:

   ```sh
   python3 "$SYNTH" make chime --out chime.wav --param decay_ms=500 --param tone_hz=1175 --param level_db=-4
   python3 "$PROBE" probe chime.wav --json
   ```

4. Compare the measurements with the brief. Change one parameter, make a new file under a new name, probe again. Stop when the numbers match the brief, or after about six rounds and tell the user what is still off.
5. Same preset, same parameters, same `--seed` gives the same samples every time, so a result can be reproduced. The default seed is 1. A `level_db` above 0 clips on purpose, which is how you make a test file for the clipping check.

## How to read the numbers

| Field | Read it as | Careful |
|---|---|---|
| `level.peak_dbfs` | Loudest sample. -120 means digital silence. | Sample peak, not true peak. |
| `level.rms_dbfs` | Plain RMS of the whole file. | A full-scale sine reads -3.01. |
| `loudness.active_rms_dbfs` | RMS of the non-silent part. | **Estimate. Not LUFS.** No K-weighting. |
| `clipping.runs` | Stretches of 3+ samples stuck at full scale. | Misses clipping that was turned down afterwards. |
| `silence.leading_s`, `trailing_s` | Quiet before and after the sound. | Threshold is -60 dBFS. |
| `silence.gaps` | Quiet stretches of 0.3 s or more inside the audio. | Information, not a fault. Compare with the intent. |
| `events.onsets_s` | When the energy jumps by 6 dB or more. | A hit hidden under a loud tail is missed. |
| `events.decay_ms` | Time for the level to fall 20 dB after the peak. | 20 ms resolution. |
| `tempo.bpm` | Pulse from the onset pattern. | **Estimate.** May be double or half. `null` means no steady pulse. |
| `spectrum.centroid_hz` | Where the energy sits on average. | **Estimate** from at most 64 frames. |
| `stereo.correlation` | 1 identical, 0 unrelated, -1 opposite. | Below -0.2 is flagged. |
| `sync.cuts[].offset_ms` | Onset minus cut. Positive is late. | The onset is where the waveform reaches 10% of its local peak. |

`summary` is one line built from these numbers by fixed rules. It is inference, never hearing. Always label it that way.

## Targets by use

Rules of thumb, mine, not standards. If the user gives a number, theirs wins. The full table is in `references/rules-of-thumb.md`.

| Use | Peak | Length and shape | Timing |
|---|---|---|---|
| UI sound | -6 to -3 dBFS, no clipping | 30 to 500 ms, decay under 300 ms | Under 10 ms of leading silence |
| Film or demo cue | -6 to -1 dBFS | Hits decay 150 to 600 ms | Onset within 40 ms of the cut |
| Music bed | -3 dBFS or lower | Long, no gaps unless intended | Tempo matches the edit, if there is one |

## Output

Hand back, in this order:

1. **Verdict**: one sentence. Clean, or the findings in plain words (for example "clipping: 12 runs, first at 0.001 s").
2. **Numbers**: a short table of only the fields that answer the question, with units. Do not paste the whole JSON.
3. **Sounds like**: the `summary` line, labelled "inferred from measurements, not heard".
4. **Estimates and gaps**: name every estimate you used (loudness, tempo, spectrum, summary) and anything you did not measure.
5. **Next step**: the one change you would make, as a parameter or an edit, and that you will re-probe it.

`examples/sample-session.md` is a real session with this format at the end. `examples/sample-probe.json` is the full JSON of one probe.

## Edge cases and errors

| Situation | What to do |
|---|---|
| Exit code 2, "not a RIFF/WAVE file" | It is not a WAV. Ask for a WAV, or offer to convert it with a tool the user already has. Do not install one. |
| Exit code 2, "Convert to PCM WAV" | Compressed audio inside a WAV wrapper. Same as above. |
| Exit code 2, "no audio frames" or "no data chunk" | Empty or cut-off file. Say so. Do not guess its contents. |
| Exit code 2, "NaN or Inf" | Corrupt float samples. Say so. |
| Exit code 2, "finite values only" | An option was nan, infinite or out of range. `--silence-db` must be 0 or below, at most 200 cuts. Fix the value and rerun. |
| Exit code 2, "not a regular file" | The path is a folder, pipe or device. Ask for the WAV file itself. |
| Finding `truncated` | The header promises more audio than the file holds. The numbers cover what is there. Say it first. |
| Finding `silent` | Nothing above -60 dBFS. Try `--silence-db -80` before you call it silent. |
| Note `capped` | Only the first 1200 s were read. Say which part you measured. |
| `tempo.bpm` is `null` | Say "no steady pulse found". Do not offer a number. |
| `sync` fails with "no onset within 500 ms" | The sound is far from the cut, missing, or too quiet to register. Look at `events.onsets_s`. |
| More than two channels | Measured, but `stereo` is `null`. Say that phase was not checked. |
| `sfx_synth` exit code 2 | Read the one-line error. It names the valid presets, parameters or ranges. |
| "already exists" | Choose a new `--out`. Use `--force` only if the user asked to replace that file. |

## Rules

- Never claim to hear anything. Say "the measurements show", "inferred", "estimated".
- Say when a number is an estimate: loudness, tempo, spectrum and `summary` always are.
- Never call the loudness figure LUFS. It is plain RMS.
- Never overwrite the user's original file. Write changes to a new file.
- No taste judgements. This skill cannot say a sound is pleasant, expensive or cheap. It can say it is 4 dB louder or 80 ms late.
- Probe before you explain, and probe again after every change. Do not predict a number you could measure.
- Change one parameter per round when tuning, so you know what moved the number.
- Never install software, never edit the scripts, and delete the temporary copies when you finish.
