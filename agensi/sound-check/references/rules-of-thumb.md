# Rules of thumb

Mine, not standards. They are starting points for a brief nobody wrote numbers for. The moment the user gives a number, use
theirs. Levels are `audio_probe.py` fields; the loudness figure is a plain RMS estimate, not LUFS, so the targets below that
use it are for comparing files made the same way.

## By use

| Check | UI sound (click, tap, notification) | Film or demo cue (hit, whoosh, riser) | Music bed |
|---|---|---|---|
| `level.peak_dbfs` | -6 to -3 | -6 to -1 | -3 or lower |
| `clipping.runs` | 0 | 0 | 0 |
| `level.dc_offset` | under 0.005 | under 0.01 | under 0.01 |
| `silence.leading_s` | under 0.010 | the cue's own lead-in, on purpose | whatever the edit needs |
| `format.duration_s` | 0.03 to 0.5 | 0.2 to 3 | the length of the edit |
| `events.decay_ms` | under 300 | hits 150 to 600 | not relevant |
| `events.attack_ms` | under 10 | hits under 10, risers as long as the rise | not relevant |
| `spectrum.centroid_hz` | clicks above 2000, soft taps below | hits 100 to 2000, whooshes above 3000 | depends on the track |
| `stereo.correlation` | 1 (mono is fine) | above 0 | above 0 |
| `sync` offset | not applicable | within 40 ms, within 20 ms for a hard hit | not applicable |
| `silence.gaps` | none | only where you planned silence | none unless planned |

## Why these numbers

- **Peak -6 to -3 dBFS** leaves head room. Another sound mixed on top will not push it into clipping.
- **Zero clipping runs** because clipping is audible as a crackle and it cannot be undone. A single sample at full scale is a
  peak, not a fault.
- **Leading silence under 10 ms** for a UI sound, because a button should not feel like it lags. 10 ms is a rule I chose.
- **40 ms sync tolerance** is the default of the probe. In my experience a sound that arrives before the picture is noticed
  sooner than one that arrives after, so tighten the early side first. Treat it as a default, not a law.
- **Decay under 300 ms** for a UI sound so it is gone before the next one can overlap.
- **Mono compatibility** matters if the audio might be played on a phone speaker or summed to mono. Correlation below 0 means
  some content cancels there.

## When a measurement and the brief disagree

1. Check the measurement is the right one. A sound with a long quiet tail can read a long `decay_ms` or none at all.
2. Check the limit in `measurements.md`. An estimate is not a verdict.
3. Change one thing, make a new file, probe it again.
4. If six rounds do not get there, say which number is still off and by how much. Do not describe the sound as better.

## What these rules cannot tell you

Whether a sound is pleasant, appropriate, expensive-sounding, annoying or on brand. There is no model in these scripts. They
count and measure.
