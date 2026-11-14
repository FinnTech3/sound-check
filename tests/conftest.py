"""Synthetic WAV builders and runners. Nothing here touches the network or a real recording."""

import json
import math
import random
import struct
from array import array

import pytest

RATE = 44100


def write_wav(path, chans, rate=RATE, bits=16, kind="int", extensible=False, data_size=None, cut=0):
    """Write channels (lists of floats in -1..1) as a WAV. `cut` drops that many bytes from the end of the data
    while the header still claims the full length. `data_size` overrides the declared data length."""
    ch, n = len(chans), len(chans[0])
    if kind == "float":
        data = array("f" if bits == 32 else "d", [c[i] for i in range(n) for c in chans]).tobytes()
    elif bits == 8:
        data = bytes(max(0, min(255, round(c[i] * 127) + 128)) for i in range(n) for c in chans)
    elif bits == 16:
        data = array("h", [max(-32768, min(32767, round(c[i] * 32767))) for i in range(n) for c in chans]).tobytes()
    elif bits == 24:
        data = b"".join(
            struct.pack("<i", max(-8388608, min(8388607, round(c[i] * 8388607))))[:3] for i in range(n) for c in chans
        )
    else:
        data = array("i", [max(-(2**31), min(2**31 - 1, round(c[i] * (2**31 - 1)))) for i in range(n) for c in chans]).tobytes()
    align, tag = ch * bits // 8, 3 if kind == "float" else 1
    if extensible:
        fmt = struct.pack("<HHIIHHHHIH14s", 0xFFFE, ch, rate, rate * align, align, bits, 22, bits, 3, tag, b"\x00" * 14)
    else:
        fmt = struct.pack("<HHIIHH", tag, ch, rate, rate * align, align, bits)
    declared = len(data) if data_size is None else data_size
    body = data[: len(data) - cut]
    blob = b"RIFF" + struct.pack("<I", 4 + 8 + len(fmt) + 8 + len(body)) + b"WAVE"
    blob += b"fmt " + struct.pack("<I", len(fmt)) + fmt + b"data" + struct.pack("<I", declared) + body
    path.write_bytes(blob)
    return path


def sine(freq, secs, rate=RATE, amp=0.5):
    return [amp * math.sin(2 * math.pi * freq * i / rate) for i in range(round(secs * rate))]


def silence(secs, rate=RATE):
    return [0.0] * round(secs * rate)


def noise(secs, rate=RATE, amp=0.3, seed=3):
    rng = random.Random(seed)
    return [amp * (rng.random() * 2 - 1) for _ in range(round(secs * rate))]


def clicks(times, secs, rate=RATE, amp=0.8):
    """Sharp decaying clicks starting exactly at the given times."""
    x = [0.0] * round(secs * rate)
    for t in times:
        i = round(t * rate)
        for k in range(40):
            if i + k < len(x):
                x[i + k] += amp * math.exp(-k / 6) * (1 if k % 2 == 0 else -1)
    return x


def decaying_sine(freq, decay_ms, secs, rate=RATE, amp=0.8):
    """Sine whose envelope falls 20 dB after decay_ms."""
    return [amp * 10 ** (-(i / rate) / (decay_ms / 1000)) * math.sin(2 * math.pi * freq * i / rate)
            for i in range(round(secs * rate))]


@pytest.fixture
def probe(capsys):
    """probe(path, *args) -> (exit code, parsed JSON). Pass text=True to get the text report instead."""
    import audio_probe

    def run(path, *args, text=False):
        code = audio_probe.main(["probe", str(path), *([] if text else ["--json"]), *args])
        out = capsys.readouterr()
        return code, (out.out if text else (json.loads(out.out) if out.out.strip() else None)), out.err

    return run
