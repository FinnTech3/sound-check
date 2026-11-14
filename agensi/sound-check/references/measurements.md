# What each measurement means, and where it stops being true

Every number comes from `audio_probe.py probe FILE.wav --json`. Times are in seconds unless the name ends in `_ms`.
Levels are dBFS: 0 is the loudest a file can hold, and everything real is negative.

A measurement is a fact about the samples. An estimate is a guess built from facts. The JSON lists the estimates in
`estimates`: `loudness`, `tempo`, `spectrum`, `summary`.

## How much of the file is read

The probe reads at most `--max-seconds` of audio, default 1200 (20 minutes). Past that it stops and adds a note
(`capped`). `format.duration_s` is the whole file, `format.analysed_s` is what was measured. Everything below describes the
analysed part.

Cost is bounded by that cap and two more: the spectrum uses at most 64 frames, and the tempo reads at most 120 s from the
middle of the file. On the machine I built this on, 10 minutes of 44.1 kHz stereo took about 5 seconds. A short sound takes
a fraction of a second. The FFT is plain Python, which is why the frame count is capped.

## format

| Field | Meaning |
|---|---|
| `sample_rate`, `channels`, `bit_depth` | Straight from the header. |
| `sample_format` | `int` (PCM) or `float`. |
| `duration_s`, `analysed_s` | Whole file and measured part. |

Supported: PCM 8, 16, 24 and 32-bit, float 32 and 64-bit, up to 8 channels, including the extensible header. Anything else
is exit code 2. A header that claims more audio than the file holds is analysed as far as the data goes and raises the
`truncated` finding. A streaming-style header (data length `0xFFFFFFFF`) is read to the end of the file without a finding.

## level

| Field | Meaning | Limit |
|---|---|---|
| `peak_dbfs` | Loudest single sample, any channel. `-120.0` means digital silence. | A sample peak. Between samples the waveform can go higher (a true peak), by a dB or two on some material. |
| `peak_time_s` | Where that sample is. | |
| `rms_dbfs` | Root-mean-square level of the whole analysed file, all channels averaged. A full-scale sine reads -3.01. | Silence drags it down. Compare with `loudness`. |
| `dc_offset` | The largest per-channel mean, as a fraction of full scale, always positive. Above 0.01 (1%) is a finding. | Says nothing about low-frequency rumble that is not constant. |

## loudness (estimate)

`active_rms_dbfs` is a plain RMS taken over 400 ms blocks every 100 ms. Blocks below -70 dBFS are dropped, then blocks more
than 10 dB under the average of what is left are dropped, and the rest are averaged as power.

That is the gating idea from the broadcast loudness standard, **without** its frequency weighting. It is not LUFS and must
never be called LUFS. A bass-heavy sound reads louder here than a real loudness meter would say. On short or decaying
sounds the blocks at the edges are counted fewer times than the middle, so it can differ from `rms_dbfs` by a dB or two in
either direction. Use it to compare two files made the same way, not to hit a loudness target. For a real LUFS figure use a
proper meter.

## clipping

`runs` counts stretches of 3 or more consecutive samples sitting on the same rail: within one step of full scale for 16-bit
and above, exactly at it for 8-bit, and at 1.0 or beyond for float. A positive rail followed directly by a negative one is
two runs, so a square wave that is clipped everywhere counts every flat top and bottom.

| Field | Meaning |
|---|---|
| `runs`, `longest_run` | How many stretches and the longest in samples. |
| `full_scale_samples` | Every sample on a rail, including lone ones. |
| `first_s` | Where the first run starts. `null` if none. |
| `over_full_scale` | Float files only: the peak is above 1.0, so the file will clip when it is converted to integer. |

Limits: one sample at full scale is a peak, not clipping, so it does not count as a run. Clipping that happened earlier and
was turned down afterwards leaves flat tops that are no longer at full scale, and this check will not find them.

## silence

Silence is a 5 ms block whose RMS is below `threshold_dbfs` (default -60, set with `--silence-db`).

| Field | Meaning | Limit |
|---|---|---|
| `leading_s` | Time before the sound starts, refined to the sample where the waveform reaches 10% of its local peak. | A soft fade-in starts "late" by this rule. |
| `trailing_s` | Time after the last loud block. | 5 ms resolution. |
| `active_s` | First loud block to last loud block. | |
| `gaps` | Pairs `[start, end]` of quiet stretches of 0.3 s or more between loud blocks, first 10 only. `gaps_total` is the full count. | A gap is information, not a fault. A click track has one between every click. |

## events

An onset is a block where the energy of the next 20 ms is at least 6 dB above the energy of the previous 20 ms, and loud
enough to be within 50 dB of the loudest block. Onsets closer than 50 ms are merged into the strongest. The reported time is
refined to the sample where the waveform first reaches 10% of its local peak (and clears 1.5 times the level just before it).

| Field | Meaning | Limit |
|---|---|---|
| `count`, `onsets_s` | Number of onsets and their times (first 500). | A hit that lands under the tail of a louder one does not rise 6 dB, so it is missed. A slow swell has a vague onset. |
| `attack_ms` | From the last onset before the loudest sample (or from the start of the sound, if there is none) to that sample. | Long for a swell, a few ms for a hit. |
| `decay_ms` | From the loudest sample until the level has fallen 20 dB, stopping at the next onset. `null` if that never happens. | Measured on 20 ms windows, so under about 40 ms read it as "very short", not as a number. |

`decay_ms` is the same quantity as the `decay_ms` parameter of `sfx_synth.py`: the time for the envelope to fall 20 dB. That
is why the two can be compared directly.

## tempo (estimate)

The onset-strength curve is smoothed and autocorrelated over lags that cover 50 to 220 BPM. If the half-lag peak is at least
60% as strong as the best one, the shorter lag is chosen, to avoid reporting half time for an obvious pulse. The peak is
refined by parabolic interpolation.

`confidence` is how far the best peak stands above the average autocorrelation, from 0 to 1. Below 0.50, or with fewer than 6
onsets, or under a few seconds of audio, the answer is `bpm: null` and a note that starts "not enough rhythm". That is the
honest answer for a single hit, a sustained tone, steady noise and irregular timing.

Limits: it can still be double or half the tempo a person would tap. Syncopated music, tempo changes and rhythm carried by
quiet onsets (see the limit under events) can fool it. It looks at 120 s at most.

## spectrum (estimate)

Up to 64 Hann-windowed frames of 2048 samples, 50% overlap, taken from the non-silent part and only from frames within 30 dB
of the loudest, mixed down to mono with the mean removed. Their power spectra are averaged.

| Field | Meaning | Limit |
|---|---|---|
| `centroid_hz` | Power-weighted mean frequency from 20 Hz up. Higher is brighter. | Dominated by the loud frames. |
| `band_percent` | Share of power in `bass` 20-150 Hz, `low_mid` 150-600, `mid` 600-2400, `high_mid` 2400-6000 and `high` 6000 Hz up. Adds to 100. | Bands above half the sample rate are empty. |
| `peakiness_log10` | Log10 of the strongest bin over the average bin, weighted by frame power. 2.2 or more reads as tonal, under 1.8 as noise-like. | A heuristic. Band-limited noise sits in between. |
| `strongest_hz` | Frequency of the strongest bin of the mean spectrum, interpolated. | A frame is 46 ms at 44.1 kHz, so low pitches are only good to a few Hz. |
| `sweep_hz` | `[start, end]` if the strongest bin in the first third of the frames and in the last third differ by more than 1.5 times. Otherwise `null`. | |
| `frames_used` | How many frames went in (at most 64). | A long file is sampled, not read in full. |

## stereo

Only for two-channel files with sound in both channels. `correlation` is how alike the channels are over the whole file: 1
identical, 0 unrelated, -1 opposite. `mono_change_db` is the level change when both are summed to mono, against the average
channel: 0 for identical channels, about -3 for unrelated ones, and a very large negative number for opposite ones (the floor is -120). A correlation
below -0.2 raises `mono_compat`. `null` for mono files, files with a silent channel, and files with more than two channels.

## sync

For each `--cuts` time, the nearest onset is found. `offset_ms` is onset minus cut: positive means the sound is late, negative
early. It passes if the absolute offset is within `--tolerance-ms` (default 40). If no onset is within 500 ms of the cut,
`offset_ms` is `null`, the cut fails, and the message says so. A quiet sound can fail that way because it never registered as an
onset: look at `events.onsets_s` and, if you must, retry with the sound isolated.

## summary (estimate)

One line from fixed rules, never from listening:

- Shape: "N onsets at about X BPM" if there is a tempo; "N separate events" for three or more onsets; "swell building for X ms" if
  the attack is 150 ms or more; "sustained sound" if the level never falls 20 dB; "very short click" under 40 ms of decay;
  "short transient" up to 600 ms; "long-tailed transient" beyond.
- Brightness from the centroid: under 400 Hz dark, to 1500 warm, to 3500 mid-range, to 6000 bright, above that very bright.
- Tone from the peakiness: tonal near X Hz, noise-like, or tonal and noisy. A sweep reads "tone sweeping X to Y Hz".
- "clipped" if there are clipping runs.

## findings

`findings` is the list that sets exit code 1: `clipping`, `dc_offset`, `silent`, `truncated`, `mono_compat`, `sync`. `notes` is
information: a capped read, interior silent gaps.
