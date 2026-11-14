#!/usr/bin/env python3
"""Synthesise simple sound effects from code and write them as 16-bit mono WAV. Standard library only.

    python3 sfx_synth.py list [--json]
    python3 sfx_synth.py make PRESET --out FILE.wav [--seed N] [--duration S] [--param key=value ...] [--rate HZ]

Deterministic: the same preset, parameters, seed and rate give the same samples (all noise comes from a seeded
generator). It writes only to the --out path, and refuses to overwrite an existing file unless --force is given.
Exit codes: 0 written, 2 bad input.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import random
import struct
import sys
from array import array

TAU = 2 * math.pi
COMMON = {
    "level_db": (-6.0, -60.0, 24.0, "peak level in dBFS after scaling; above 0 clips on purpose"),
    "delay_ms": (0.0, 0.0, 20000.0, "silence before the sound starts"),
}
PRESETS = {
    "click": ("short broadband transient: a fast-decaying noise burst over a ring", 0.12, {
        "ring_hz": (3500.0, 200.0, 12000.0, "pitch of the ring under the noise"),
        "decay_ms": (8.0, 1.0, 500.0, "time to fall 20 dB"),
        "noise": (0.5, 0.0, 1.0, "noise share against the ring, 0 to 1")}),
    "tick": ("tiny tonal tick, like a clock or a UI step", 0.15, {
        "tone_hz": (1800.0, 200.0, 12000.0, "pitch of the tick"),
        "decay_ms": (25.0, 2.0, 1000.0, "time to fall 20 dB")}),
    "pop": ("soft bubble pop: a quick downward sweep with a short tail", 0.25, {
        "from_hz": (900.0, 100.0, 8000.0, "pitch at the start"),
        "to_hz": (250.0, 40.0, 8000.0, "pitch the sweep settles on"),
        "sweep_ms": (40.0, 2.0, 500.0, "sweep time constant"),
        "decay_ms": (60.0, 5.0, 2000.0, "time to fall 20 dB")}),
    "thump": ("low body thump: a sine that falls in pitch, plus a small click", 0.6, {
        "from_hz": (110.0, 30.0, 400.0, "pitch at the start"),
        "to_hz": (48.0, 20.0, 300.0, "pitch the drop settles on"),
        "sweep_ms": (60.0, 5.0, 500.0, "drop time constant"),
        "decay_ms": (180.0, 20.0, 3000.0, "time to fall 20 dB"),
        "click": (0.2, 0.0, 1.0, "share of a 3 ms noise click at the start")}),
    "whoosh": ("filtered noise whose band rises and falls: a pass-by", 0.9, {
        "low_hz": (300.0, 50.0, 4000.0, "band centre at the quiet ends"),
        "high_hz": (4000.0, 500.0, 12000.0, "band centre at the loudest point"),
        "peak": (0.4, 0.1, 0.9, "where the loudest point falls, 0 to 1 of the duration"),
        "q": (1.5, 0.5, 8.0, "resonance: higher is narrower")}),
    "riser": ("rising sweep with noise that grows louder to the end", 2.0, {
        "from_hz": (200.0, 40.0, 4000.0, "pitch at the start"),
        "to_hz": (3000.0, 200.0, 12000.0, "pitch at the end"),
        "noise": (0.35, 0.0, 1.0, "noise share, 0 to 1")}),
    "hit": ("impact: a low body with a noise burst on top", 1.0, {
        "body_hz": (65.0, 25.0, 300.0, "pitch of the body"),
        "noise": (0.6, 0.0, 1.0, "noise share against the body, 0 to 1"),
        "cutoff_hz": (5000.0, 300.0, 12000.0, "noise brightness (one-pole low-pass)"),
        "decay_ms": (350.0, 20.0, 5000.0, "time to fall 20 dB")}),
    "chime": ("struck bell: four inharmonic partials that ring out", 1.6, {
        "tone_hz": (880.0, 100.0, 4000.0, "pitch of the lowest partial"),
        "decay_ms": (900.0, 50.0, 8000.0, "time for the lowest partial to fall 20 dB"),
        "bright": (0.5, 0.0, 1.0, "level of the upper partials, 0 to 1")}),
    "drop": ("pitch drop: a long downward sweep that fades out", 1.2, {
        "from_hz": (600.0, 100.0, 4000.0, "pitch at the start"),
        "to_hz": (50.0, 20.0, 400.0, "pitch at the end of the sweep"),
        "sweep_ms": (700.0, 50.0, 5000.0, "length of the sweep"),
        "decay_ms": (800.0, 50.0, 8000.0, "time to fall 20 dB")}),
}


class BadInput(Exception):
    """A user mistake: one line, exit 2."""


def env(t, ms):
    """Exponential decay that falls 20 dB after `ms` milliseconds."""
    return 10 ** (-t / (ms / 1000))


def sweep(n, sr, hz):
    """Sine whose frequency follows hz(t), integrated into phase."""
    ph, out = 0.0, []
    for i in range(n):
        out.append(math.sin(ph))
        ph += TAU * hz(i / sr) / sr
    return out


def attack(t):
    return min(1.0, t / 0.0005)


def noise(rng):
    return rng.random() * 2 - 1


def bell(u, peak):
    """0 at both ends, 1 at `peak`, smooth in between."""
    return math.sin(math.pi * (u / (2 * peak) if u < peak else 0.5 + (u - peak) / (2 * (1 - peak)))) ** 2


def gen_click(p, n, sr, rng):
    return [env(i / sr, p["decay_ms"]) * min(1.0, i / sr / 0.0002) *
            (p["noise"] * noise(rng) + (1 - p["noise"]) * math.sin(TAU * p["ring_hz"] * i / sr)) for i in range(n)]


def gen_tick(p, n, sr, rng):
    return [env(i / sr, p["decay_ms"]) * attack(i / sr) * (math.sin(TAU * p["tone_hz"] * i / sr) +
            0.3 * math.sin(TAU * 2.01 * p["tone_hz"] * i / sr)) for i in range(n)]


def gen_pop(p, n, sr, rng):
    s = sweep(n, sr, lambda t: p["to_hz"] + (p["from_hz"] - p["to_hz"]) * math.exp(-t / (p["sweep_ms"] / 1000)))
    return [v * env(i / sr, p["decay_ms"]) * attack(i / sr) for i, v in enumerate(s)]


def gen_thump(p, n, sr, rng):
    s = sweep(n, sr, lambda t: p["to_hz"] + (p["from_hz"] - p["to_hz"]) * math.exp(-t / (p["sweep_ms"] / 1000)))
    ck = p["click"]
    return [(1 - ck) * v * env(i / sr, p["decay_ms"]) * attack(i / sr) + ck * noise(rng) * env(i / sr, 3)
            for i, v in enumerate(s)]


def gen_whoosh(p, n, sr, rng):
    out, low, band = [], 0.0, 0.0
    for i in range(n):
        u = i / max(1, n - 1)
        b = bell(u, p["peak"])
        fc = p["low_hz"] * (p["high_hz"] / p["low_hz"]) ** b
        f = 2 * math.sin(math.pi * fc / sr)
        low += f * band
        band += f * (noise(rng) - low - band / p["q"])
        out.append(band * b)
    return out


def gen_riser(p, n, sr, rng):
    s = sweep(n, sr, lambda t: p["from_hz"] * (p["to_hz"] / p["from_hz"]) ** (t * sr / max(1, n - 1)))
    return [((1 - p["noise"]) * v + p["noise"] * noise(rng)) * (i / max(1, n - 1)) ** 2 for i, v in enumerate(s)]


def gen_hit(p, n, sr, rng):
    out, lp, a = [], 0.0, 1 - math.exp(-TAU * p["cutoff_hz"] / sr)
    for i in range(n):
        t = i / sr
        lp += a * (noise(rng) - lp)
        out.append((1 - p["noise"]) * math.sin(TAU * p["body_hz"] * t) * env(t, p["decay_ms"]) +
                   p["noise"] * lp * env(t, p["decay_ms"] * 0.5))
    return [v * attack(i / sr) for i, v in enumerate(out)]


def gen_chime(p, n, sr, rng):
    parts = ((1.0, 1.0), (2.76, 0.5 * p["bright"]), (5.4, 0.3 * p["bright"]), (8.93, 0.15 * p["bright"]))
    f0, d = p["tone_hz"], p["decay_ms"]
    return [attack(i / sr) * sum(a * env(i / sr, d / (1 + 0.5 * k)) * math.sin(TAU * r * f0 * i / sr)
            for k, (r, a) in enumerate(parts) if r * f0 < sr / 2) for i in range(n)]


def gen_drop(p, n, sr, rng):
    d = p["sweep_ms"] / 1000
    s = sweep(n, sr, lambda t: p["to_hz"] * (p["from_hz"] / p["to_hz"]) ** max(0.0, 1 - t / d))
    return [v * env(i / sr, p["decay_ms"]) * attack(i / sr) for i, v in enumerate(s)]


GENERATORS = {name: globals()["gen_" + name] for name in PRESETS}


def render(preset, params, seed, duration, rate):
    """Samples as ints plus a report. Everything random comes from random.Random(seed)."""
    spec = PRESETS[preset]
    p = {k: v[0] for k, v in {**spec[2], **COMMON}.items()}
    for key, val in params.items():
        if key not in {**spec[2], **COMMON}:
            raise BadInput(f"{preset} has no parameter {key!r}. Valid: {', '.join({**spec[2], **COMMON})}")
        lo, hi = {**spec[2], **COMMON}[key][1:3]
        if not lo <= val <= hi:
            raise BadInput(f"{key}={val:g} is outside {lo:g} to {hi:g}")
        if key.endswith("_hz") and val >= rate / 2:
            raise BadInput(f"{key}={val:g} is at or above half the sample rate ({rate / 2:g} Hz)")
        p[key] = val
    total, lead = round(duration * rate), round(p["delay_ms"] * rate / 1000)
    if total - lead < rate // 100:
        raise BadInput("--duration leaves less than 10 ms after delay_ms: lengthen it")
    body = GENERATORS[preset](p, total - lead, rate, random.Random(seed))
    fade = min(len(body), round(0.004 * rate))
    for i in range(fade):
        body[len(body) - 1 - i] *= i / fade
    peak = max(abs(v) for v in body) or 1.0
    gain = 10 ** (p["level_db"] / 20) / peak
    q = [0] * lead + [max(-32768, min(32767, round(v * gain * 32767))) for v in body]
    top = max(abs(v) for v in q)
    peak_db = round(20 * math.log10(top / 32768), 2) if top else None
    clipped = sum(1 for v in q if v >= 32767 or v <= -32768)
    return q, {"preset": preset, "seed": seed, "sample_rate": rate, "frames": total,
               "duration_s": round(total / rate, 4), "peak_dbfs": peak_db, "clipped_samples": clipped, "params": p}


def wav_bytes(q, rate):
    data = array("h", q)
    if sys.byteorder == "big":
        data.byteswap()
    data = data.tobytes()
    fmt = struct.pack("<IHHIIHH", 16, 1, 1, rate, rate * 2, 2, 16)
    head = b"RIFF" + struct.pack("<I", 36 + len(data)) + b"WAVEfmt " + fmt
    return head + b"data" + struct.pack("<I", len(data)) + data


def write_new(path, blob, force):
    """Create `path` and write the bytes. Without force the create fails if the file exists."""
    flags = os.O_WRONLY | os.O_CREAT | (os.O_TRUNC if force else os.O_EXCL) | getattr(os, "O_BINARY", 0)
    try:
        fd = os.open(path, flags, 0o644)
    except FileExistsError:
        raise BadInput(f"{path} already exists: choose another name, or pass --force to replace it") from None
    except OSError as e:
        raise BadInput(f"cannot write {path}: {e.strerror or e}") from None
    try:
        view = memoryview(blob)
        while view:
            view = view[os.write(fd, view) :]
    except OSError as e:
        os.close(fd)
        os.unlink(path)
        raise BadInput(f"cannot write {path}: {e.strerror or e}") from None
    os.close(fd)


def spec_json(table):
    return {n: {"default": d[0], "min": d[1], "max": d[2], "meaning": d[3]} for n, d in table.items()}


def show_list(as_json):
    if as_json:
        presets = {k: {"description": v[0], "default_duration_s": v[1], "params": spec_json(v[2])}
                   for k, v in PRESETS.items()}
        return json.dumps({"presets": presets, "common_params": spec_json(COMMON)}, indent=2)
    lines = []
    for name, (text, dur, params) in PRESETS.items():
        lines.append(f"{name}: {text} (default {dur} s)")
        lines += [f"    {n}={d[0]:g} ({d[1]:g} to {d[2]:g})  {d[3]}" for n, d in params.items()]
    lines.append("every preset also takes:")
    lines += [f"    {n}={d[0]:g} ({d[1]:g} to {d[2]:g})  {d[3]}" for n, d in COMMON.items()]
    lines.append("--duration S sets the file length, --seed N the noise, --rate HZ the sample rate (22050 to 96000)")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="sfx_synth.py", description="Synthesise sound effects as WAV files.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="show presets and parameters").add_argument("--json", action="store_true")
    mk = sub.add_parser("make", help="write a preset to a WAV file")
    mk.add_argument("preset")
    mk.add_argument("--out", required=True, help="WAV file to create")
    mk.add_argument("--seed", type=int, default=1, help="noise seed (default 1)")
    mk.add_argument("--duration", type=float, help="total length in seconds (default depends on the preset)")
    mk.add_argument("--param", action="append", default=[], metavar="KEY=VALUE", help="override a parameter")
    mk.add_argument("--rate", type=int, default=44100, help="sample rate in Hz (default 44100)")
    mk.add_argument("--force", action="store_true", help="replace --out if it exists")
    mk.add_argument("--json", action="store_true", help="print the report as JSON")
    o = ap.parse_args(argv)
    if o.cmd == "list":
        print(show_list(o.json))
        return 0
    try:
        if o.preset not in PRESETS:
            raise BadInput(f"unknown preset {o.preset!r}. Presets: {', '.join(PRESETS)}")
        if not 22050 <= o.rate <= 96000:
            raise BadInput("--rate must be between 22050 and 96000")
        dur = PRESETS[o.preset][1] if o.duration is None else o.duration
        if not 0.01 <= dur <= 60:
            raise BadInput("--duration must be between 0.01 and 60 seconds")
        params = {}
        for text in o.param:
            key, eq, val = text.partition("=")
            try:
                if not eq:
                    raise ValueError
                params[key.strip()] = float(val)
            except ValueError:
                raise BadInput(f"--param wants KEY=NUMBER, got {text!r}") from None
        q, report = render(o.preset, params, o.seed, dur, o.rate)
        write_new(o.out, wav_bytes(q, o.rate), o.force)
    except BadInput as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    report["file"] = o.out
    if o.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"wrote {o.out}: {o.preset}, seed {o.seed}, {report['duration_s']} s at {o.rate} Hz, 16-bit mono, "
              f"peak {report['peak_dbfs']} dBFS, {report['clipped_samples']} samples at full scale")
        print("params: " + ", ".join(f"{k}={v:g}" for k, v in report["params"].items()))
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(errors="replace")
    sys.exit(main())
