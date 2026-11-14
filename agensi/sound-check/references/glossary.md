# Glossary

**Attack.** How long the sound takes to rise from its start to its loudest point. A click has a very short attack. A riser has a
long one. `events.attack_ms`.

**Band.** A slice of the frequency range. The probe splits energy into five: bass, low-mid, mid, high-mid and high.

**BPM.** Beats per minute. The probe estimates it from the pattern of onsets and says "not enough rhythm" when there is no
steady pulse.

**Centroid.** The average frequency of the energy, weighted by power. A high centroid sounds bright, a low one dark. A summary
number, not a pitch.

**Clipping.** The waveform hits the highest or lowest value the file can hold and is flattened. In the probe, a run of 3 or more
samples on the same limit. It sounds like crackle or harshness.

**Correlation.** For stereo, how alike left and right are: 1 the same, 0 unrelated, -1 opposite.

**Cut.** A point in the picture where one shot changes to another. A sound that belongs to it should start there.

**dBFS.** Decibels relative to full scale. 0 dBFS is the loudest value a digital file can hold. A level of -6 dBFS is half the
amplitude of 0.

**DC offset.** The waveform sits above or below zero on average instead of swinging around it. It wastes head room and can click
at starts and stops.

**Decay.** How long the sound takes to die away after its peak. In this skill: the time for the level to fall 20 dB.

**Digital silence.** Every sample exactly zero. The probe shows its peak as -120.

**FFT.** The calculation that turns a short stretch of samples into energy per frequency. The probe runs one in plain Python on at
most 64 frames.

**Full scale.** The largest value the format can store. For 16-bit that is 32767 above zero and -32768 below.

**LUFS.** A loudness unit from a broadcast standard, which weights frequencies the way hearing does and gates out silence. The
probe does not compute it. Its loudness figure is a plain RMS.

**Mono compatibility.** Whether a stereo file still sounds right when its channels are added together. Opposite-phase content
cancels.

**Onset.** The moment a new sound starts. In the probe, where the energy of the next 20 ms is at least 6 dB above the previous
20 ms, placed at the sample where the waveform reaches 10% of its local peak.

**Peak.** The largest single sample. A sample peak can underestimate the true peak between samples.

**PCM.** Plain uncompressed samples, the usual WAV contents. Compressed audio in a WAV wrapper is refused.

**RMS.** Root mean square, the average power of the signal expressed as a level. It tracks loudness better than the peak does,
without frequency weighting.

**Sample rate.** Samples per second. 44100 means 44,100. The highest frequency a file can hold is half of it.

**Seed.** The number that fixes the noise in `sfx_synth.py`. Same preset, parameters and seed give the same samples.

**Sync.** Whether a sound starts when the picture says it should. The probe reports onset minus cut in milliseconds, positive
when the sound is late.

**Tonal.** Dominated by a few frequencies, so it has a pitch. The opposite of noise-like.

**Transient.** A short, sudden sound that rises fast and dies away, like a click or a hit.
