# Trigger tests: Sound Check

Agensi's pre-publish rule: the skill should trigger on 5 of 5 relevant prompts and 0 of 5 unrelated ones. If it
triggers on fewer than 4 relevant prompts, the description is too narrow. If it triggers on more than 1 unrelated
prompt, it is too broad.

Status: **not yet run in an agent.** Run each prompt in a fresh session with the skill installed, tick the box when
the result is right, and record the agent and date. Run again after a model update.

## Should trigger

- [ ] Is demo-audio.wav clipping anywhere?
- [ ] The hit in my film should land on the cut at 12.4 seconds. Does it, within 40 ms?
- [ ] Why is there silence in the middle of this soundtrack?
- [ ] Make a short click sound for the submit button and check that it peaks around -4 dBFS.
- [ ] Is the stereo mix in final-mix.wav going to cancel out when it is played in mono?

## Should not trigger

- [ ] Write a song about autumn and generate the audio
- [ ] Transcribe this meeting recording
- [ ] Convert interview.mp3 to a WAV file
- [ ] Does this track sound better with more bass?
- [ ] Write a Python function that computes a moving average

## Record

| Agent | Date | Relevant (of 5) | Unrelated that triggered (of 5) |
|---|---|---|---|
