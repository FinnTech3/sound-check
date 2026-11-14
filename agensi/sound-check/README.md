# Sound Check

An agent skill that gives your agent evidence about audio it cannot hear.

It measures a WAV file, and it makes simple sounds from code that the agent can tune by measuring them.

## What you get

- Peak level, clipping (runs of full-scale samples), DC offset, silence before, after and inside the sound.
- Onset times, attack and decay, a tempo estimate with a confidence figure, and an honest "not enough rhythm" when there is none.
- Brightness and a five-band energy split, from a pure-Python FFT with a bounded cost.
- Stereo correlation and a mono-compatibility warning.
- A sync check: give it cut times, and it says how many milliseconds late or early each sound lands, and whether that passes your tolerance.
- A one-line "sounds like", clearly labelled as inferred from numbers.
- Nine sound-effect presets (click, tick, pop, thump, whoosh, riser, hit, chime, drop), deterministic from a seed, with parameters the agent can change between measurements.

## What it needs

- Python 3.10 or newer. No packages, no network, no API key.
- A WAV file for the probe. For other formats, convert to WAV first. The skill never installs anything.
- Permission for your agent to run Python scripts from a temporary file. The probe only reads. The synthesiser writes one WAV, only to the path it is given, and will not overwrite an existing file unless told to.

## How to use it

Ask your agent, for example:

- "Is this audio clipping? Check demo-audio.wav."
- "Does the hit land on the cut at 1.20 seconds? Allow 40 ms."
- "Why is there silence in the middle of the soundtrack?"
- "Make a short click for the submit button, peak around -4 dBFS, and check it."

## Files

| File | Purpose |
|---|---|
| `SKILL.md` | The workflow the agent follows |
| `scripts/audio_probe.py` | Measures a WAV file. Read-only, one self-contained file |
| `scripts/sfx_synth.py` | Writes deterministic sound effects. One self-contained file |
| `references/measurements.md` | What every number means and where it stops being reliable |
| `references/rules-of-thumb.md` | Starting targets for UI sounds, film cues and music beds |
| `references/presets.md` | The nine presets and which parameter moves which measurement |
| `references/glossary.md` | The terms, in plain words |
| `examples/sample-session.md` | A real session: three sounds made and probed, one clipped, one late |
| `examples/sample-probe.json` | The full JSON of one probe |

## Limits

Measurements are not hearing. There is no model in these scripts, so no judgement of taste, quality or genre. Loudness is a plain RMS estimate and is not LUFS. Tempo and spectrum are estimates. Clipping is found only where samples sit at full scale. A sound hidden under a louder tail may not register as an onset. WAV only. Cost is bounded: at most 1200 seconds of audio are read and at most 64 spectrum frames are used.
