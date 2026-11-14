# The nine presets, and which knob moves which number

`python3 "$SYNTH" list` prints the same parameters with their defaults and ranges. Every preset also takes `level_db` (the peak
after scaling, default -6; above 0 clips on purpose) and `delay_ms` (silence before the sound starts, default 0). `--duration`
sets the file length, `--seed` the noise, `--rate` the sample rate (22050 to 96000). Every `decay_ms` is the time for the sound
to fall 20 dB, the same thing the probe's `events.decay_ms` measures.

## What each preset measures at its defaults

Probed with `audio_probe.py` at seed 1. Real output, not a target.

| Preset | Length | Decay | Attack | Centroid | Summary the probe gives |
|---|---:|---:|---:|---:|---|
| `click` | 0.12 s | 10 ms | 0.2 ms | 6338 Hz | very short click, very bright, tonal near 3501 Hz |
| `tick` | 0.15 s | 30 ms | 0.6 ms | 1950 Hz | very short click, mid-range, tonal near 1802 Hz |
| `pop` | 0.25 s | 65 ms | 0.7 ms | 617 Hz | short transient, 65 ms decay, warm, tonal and noisy |
| `thump` | 0.6 s | 185 ms | 2 ms | 79 Hz | short transient, 185 ms decay, dark, tone sweeping 86 to 43 Hz |
| `whoosh` | 0.9 s | 325 ms | 364.6 ms | 6057 Hz | swell building for 365 ms, then fading in 325 ms, very bright, noise-like |
| `riser` | 2.0 s | none | 1861.6 ms | 3380 Hz | swell building for 1862 ms, mid-range, tone sweeping 452 to 1938 Hz |
| `hit` | 1.0 s | 330 ms | 4 ms | 1172 Hz | short transient, 330 ms decay, warm, tonal near 65 Hz |
| `chime` | 1.6 s | 895 ms | 2.5 ms | 992 Hz | long-tailed transient, 895 ms decay, warm, tonal near 881 Hz |
| `drop` | 1.2 s | 810 ms | 1.1 ms | 357 Hz | long-tailed transient, 810 ms decay, dark, tone sweeping 301 to 43 Hz |

The probe's decay reads a few ms above the parameter for short sounds because it measures on 20 ms windows.

## Which parameter to change

| You want | Preset and parameter | Then check |
|---|---|---|
| A shorter or longer tail | `decay_ms` on click, tick, pop, thump, hit, chime, drop | `events.decay_ms` |
| A different pitch | `tone_hz` (tick, chime), `ring_hz` (click), `body_hz` (hit), `from_hz` and `to_hz` (pop, thump, drop, riser) | `spectrum.strongest_hz` or `sweep_hz` |
| Brighter or darker | `ring_hz`, `cutoff_hz` (hit), `bright` (chime), `high_hz` (whoosh) | `spectrum.centroid_hz`, `band_percent` |
| More or less noise | `noise` on click, hit, riser; `click` on thump | `spectrum.peakiness_log10` |
| Louder or quieter | `level_db` | `level.peak_dbfs` |
| A later start | `delay_ms` (with `--duration` long enough) | `silence.leading_s`, `events.onsets_s`, `sync` |
| A longer whoosh or riser | `--duration` | `events.attack_ms` |
| Where the whoosh peaks | `peak` (0.1 to 0.9 of the duration) | `level.peak_time_s` |
| A narrower whoosh band | `q` | `spectrum.centroid_hz` falls, `peakiness_log10` rises |

Presets are small recipes, not recordings. They give you a starting shape and a way to test a pipeline. Whether one fits a
particular film is for a person to decide.
