# A real session

This is a real run of both scripts, copied from the terminal. The only thing I changed is the path: `$SYNTH` and
`$PROBE` stand for the temporary copies of `sfx_synth.py` and `audio_probe.py`. The sounds are synthetic, so the
numbers below say nothing about recorded audio, but every number is what the scripts printed.

The brief I gave myself:

- A notification chime. Decay under 600 ms, peak between -6 and -3 dBFS, no clipping.
- A thump for a title card. It must not clip.
- A hit that lands on a picture cut at 1.20 s, within 40 ms.

## 1. The chime: make, probe, adjust, probe

First take, all defaults.

```console
$ python3 "$SYNTH" make chime --out chime.wav
wrote chime.wav: chime, seed 1, 1.6 s at 44100 Hz, 16-bit mono, peak -6.0 dBFS, 0 samples at full scale
params: tone_hz=880, decay_ms=900, bright=0.5, level_db=-6, delay_ms=0
```
(exit code 0)

```console
$ python3 "$PROBE" probe chime.wav
audio_probe: chime.wav
format    sample_rate 44100 | channels 1 | bit_depth 16 | sample_format int | duration_s 1.6 | analysed_s 1.6
level     peak_dbfs -6.0 | peak_time_s 0.0026 | rms_dbfs -21.07 | dc_offset 1e-05
loudness  active_rms_dbfs -20.81 | basis plain RMS, not LUFS (estimate)
clipping  runs 0 | longest_run 0 | full_scale_samples 0 | first_s None | over_full_scale False
silence   threshold_dbfs -60.0 | leading_s 0.0 | trailing_s 0.0 | active_s 1.601 | gaps_total 0 | gaps []
events    count 1 | onsets_s [0.0001] | attack_ms 2.5 | decay_ms 895.0
tempo     bpm None | confidence 0.0 | note not enough rhythm: 1 onsets in 1.6 s (needs 6+) (estimate)
spectrum  centroid_hz 992.2 | band_percent bass 0.0 | low_mid 0.0 | mid 95.0 | high_mid 4.8 | high 0.2 | peakiness_log10 2.8 | frames_used 59 | sweep_hz None | strongest_hz 881.4 (estimate)
Sounds like (inferred from measurements, not heard): long-tailed transient, 895 ms decay, warm, tonal near 881 Hz
findings: none
```
(exit code 0)

The decay is 895 ms. The brief says under 600 ms. The peak and the pitch are fine, so I change only the decay, plus the
pitch and level I wanted anyway, and make a second file instead of overwriting the first.

```console
$ python3 "$SYNTH" make chime --out chime2.wav --param decay_ms=500 --param tone_hz=1175 --param level_db=-4 --duration 1.0
wrote chime2.wav: chime, seed 1, 1.0 s at 44100 Hz, 16-bit mono, peak -4.0 dBFS, 0 samples at full scale
params: tone_hz=1175, decay_ms=500, bright=0.5, level_db=-4, delay_ms=0
```
(exit code 0)

```console
$ python3 "$PROBE" probe chime2.wav
audio_probe: chime2.wav
format    sample_rate 44100 | channels 1 | bit_depth 16 | sample_format int | duration_s 1.0 | analysed_s 1.0
level     peak_dbfs -4.0 | peak_time_s 0.0019 | rms_dbfs -19.67 | dc_offset 1e-05
loudness  active_rms_dbfs -20.66 | basis plain RMS, not LUFS (estimate)
clipping  runs 0 | longest_run 0 | full_scale_samples 0 | first_s None | over_full_scale False
silence   threshold_dbfs -60.0 | leading_s 0.0 | trailing_s 0.0023 | active_s 0.998 | gaps_total 0 | gaps []
events    count 1 | onsets_s [0.0001] | attack_ms 1.8 | decay_ms 495.0
tempo     bpm None | confidence 0.0 | note not enough rhythm: 1 onsets in 1.0 s (needs 6+) (estimate)
spectrum  centroid_hz 1319.4 | band_percent bass 0.0 | low_mid 0.0 | mid 95.1 | high_mid 3.8 | high 1.1 | peakiness_log10 2.71 | frames_used 33 | sweep_hz None | strongest_hz 1176.7 (estimate)
Sounds like (inferred from measurements, not heard): short transient, 495 ms decay, warm, tonal near 1177 Hz
findings: none
```
(exit code 0)

Decay 495 ms, peak -4.0 dBFS, strongest component near 1177 Hz, no findings. That matches the brief, so I stop.

## 2. The thump: a deliberately clipped file

`level_db` above 0 clips on purpose, so there is something to catch.

```console
$ python3 "$SYNTH" make thump --out thump_hot.wav --param level_db=8
wrote thump_hot.wav: thump, seed 1, 0.6 s at 44100 Hz, 16-bit mono, peak 0.0 dBFS, 1649 samples at full scale
params: from_hz=110, to_hz=48, sweep_ms=60, decay_ms=180, click=0.2, level_db=8, delay_ms=0
```
(exit code 0)

```console
$ python3 "$PROBE" probe thump_hot.wav
audio_probe: thump_hot.wav
format    sample_rate 44100 | channels 1 | bit_depth 16 | sample_format int | duration_s 0.6 | analysed_s 0.6
level     peak_dbfs 0.0 | peak_time_s 0.0053 | rms_dbfs -9.35 | dc_offset 0.00311
loudness  active_rms_dbfs -10.05 | basis plain RMS, not LUFS (estimate)
clipping  runs 12 | longest_run 156 | full_scale_samples 1649 | first_s 0.0008 | over_full_scale False
silence   threshold_dbfs -60.0 | leading_s 0.0 | trailing_s 0.0113 | active_s 0.589 | gaps_total 0 | gaps []
events    count 1 | onsets_s [0.0] | attack_ms 5.3 | decay_ms 220.0
tempo     bpm None | confidence 0.0 | note not enough rhythm: 1 onsets in 0.6 s (needs 6+) (estimate)
spectrum  centroid_hz 77.7 | band_percent bass 98.3 | low_mid 1.7 | mid 0.0 | high_mid 0.0 | high 0.0 | peakiness_log10 2.77 | frames_used 14 | sweep_hz [86, 43] | strongest_hz 73.1 (estimate)
Sounds like (inferred from measurements, not heard): short transient, 220 ms decay, dark, tone sweeping 86 to 43 Hz, clipped
FINDING [clipping] 12 full-scale runs (longest 156), first at 0.001 s
```
(exit code 1)

Exit code 1, and the finding says where: 12 runs of full-scale samples, the longest 156 samples long, the first at
0.001 s. The summary line ends in "clipped". Now the same sound at -3 dBFS.

```console
$ python3 "$SYNTH" make thump --out thump.wav --param level_db=-3
wrote thump.wav: thump, seed 1, 0.6 s at 44100 Hz, 16-bit mono, peak -3.0 dBFS, 0 samples at full scale
params: from_hz=110, to_hz=48, sweep_ms=60, decay_ms=180, click=0.2, level_db=-3, delay_ms=0
```
(exit code 0)

```console
$ python3 "$PROBE" probe thump.wav
audio_probe: thump.wav
format    sample_rate 44100 | channels 1 | bit_depth 16 | sample_format int | duration_s 0.6 | analysed_s 0.6
level     peak_dbfs -3.0 | peak_time_s 0.002 | rms_dbfs -17.94 | dc_offset 0.00165
loudness  active_rms_dbfs -18.86 | basis plain RMS, not LUFS (estimate)
clipping  runs 0 | longest_run 0 | full_scale_samples 0 | first_s None | over_full_scale False
silence   threshold_dbfs -60.0 | leading_s 0.0 | trailing_s 0.0961 | active_s 0.504 | gaps_total 0 | gaps []
events    count 1 | onsets_s [0.0] | attack_ms 2.0 | decay_ms 185.0
tempo     bpm None | confidence 0.0 | note not enough rhythm: 1 onsets in 0.6 s (needs 6+) (estimate)
spectrum  centroid_hz 79.0 | band_percent bass 100.0 | low_mid 0.0 | mid 0.0 | high_mid 0.0 | high 0.0 | peakiness_log10 2.78 | frames_used 12 | sweep_hz [86, 43] | strongest_hz 81.5 (estimate)
Sounds like (inferred from measurements, not heard): short transient, 185 ms decay, dark, tone sweeping 86 to 43 Hz
findings: none
```
(exit code 0)

No clipping, peak -3.0 dBFS, exit code 0.

## 3. The hit: a late sound caught by the sync check

The picture cuts to the title card at 1.20 s. I put the hit 1280 ms into a 3 second file, which is 80 ms late on purpose.

```console
$ python3 "$SYNTH" make hit --out hit_late.wav --duration 3 --param delay_ms=1280
wrote hit_late.wav: hit, seed 1, 3.0 s at 44100 Hz, 16-bit mono, peak -6.0 dBFS, 0 samples at full scale
params: body_hz=65, noise=0.6, cutoff_hz=5000, decay_ms=350, level_db=-6, delay_ms=1280
```
(exit code 0)

```console
$ python3 "$PROBE" probe hit_late.wav --cuts 1.20 --tolerance-ms 40
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
(exit code 1)

The onset is at 1.2802 s, so the sound is 80.2 ms after the cut. The tolerance is 40 ms, so the check fails and the exit
code is 1. The fix is to start the sound at 1200 ms.

```console
$ python3 "$SYNTH" make hit --out hit.wav --duration 3 --param delay_ms=1200
wrote hit.wav: hit, seed 1, 3.0 s at 44100 Hz, 16-bit mono, peak -6.0 dBFS, 0 samples at full scale
params: body_hz=65, noise=0.6, cutoff_hz=5000, decay_ms=350, level_db=-6, delay_ms=1200
```
(exit code 0)

```console
$ python3 "$PROBE" probe hit.wav --cuts 1.20 --tolerance-ms 40
audio_probe: hit.wav
format    sample_rate 44100 | channels 1 | bit_depth 16 | sample_format int | duration_s 3.0 | analysed_s 3.0
level     peak_dbfs -6.0 | peak_time_s 1.2042 | rms_dbfs -29.22 | dc_offset 0.00024
loudness  active_rms_dbfs -22.24 | basis plain RMS, not LUFS (estimate)
clipping  runs 0 | longest_run 0 | full_scale_samples 0 | first_s None | over_full_scale False
silence   threshold_dbfs -60.0 | leading_s 1.2002 | trailing_s 0.9846 | active_s 0.818 | gaps_total 0 | gaps []
events    count 1 | onsets_s [1.2002] | attack_ms 4.0 | decay_ms 320.0
tempo     bpm None | confidence 0.0 | note not enough rhythm: 1 onsets in 3.0 s (needs 6+) (estimate)
spectrum  centroid_hz 1325.9 | band_percent bass 79.8 | low_mid 1.3 | mid 4.8 | high_mid 5.9 | high 8.1 | peakiness_log10 2.69 | frames_used 23 | sweep_hz None | strongest_hz 64.7 (estimate)
sync      tolerance_ms 40.0 | pass True | cuts [cut_s 1.2 | offset_ms 0.2 | pass True]
Sounds like (inferred from measurements, not heard): short transient, 320 ms decay, warm, tonal near 65 Hz
findings: none
```
(exit code 0)

Offset +0.2 ms, pass, no findings.

## 4. The script will not overwrite a file

I ran the same `make` command again with the same `--out`.

```console
$ python3 "$SYNTH" make hit --out hit.wav --duration 3 --param delay_ms=1200
error: hit.wav already exists: choose another name, or pass --force to replace it
```
(exit code 2)

That is the rule for the originals too: `audio_probe.py` only reads, and `sfx_synth.py` only writes the one path you give
it, and only if nothing is there already (`--force` replaces it).

## What the agent tells the user

> **Chime.** The default take decays in 895 ms, which misses your 600 ms limit. With `decay_ms=500`, `tone_hz=1175` and
> `level_db=-4` the second take measures a decay of 495 ms, a peak of -4.0 dBFS and its strongest component near
> 1177 Hz, with no findings.
>
> **Thump.** At `level_db=8` it clips: 12 runs of full-scale samples, the longest 156 samples, the first at 0.001 s. At
> `level_db=-3` the peak is -3.0 dBFS and nothing clips.
>
> **Hit.** Against the cut at 1.20 s the first take lands at 1.2802 s: 80.2 ms late, outside the 40 ms tolerance. Starting
> it at 1200 ms puts the onset at 1.2002 s, +0.2 ms, which passes.
>
> What I did not measure: whether any of these sounds good. The "sounds like" lines are inferred from the numbers and
> I have not heard the files. The loudness figure is a plain RMS estimate, not LUFS.
