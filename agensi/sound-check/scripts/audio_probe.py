#!/usr/bin/env python3
"""Measure a WAV file: evidence an agent can reason about, not hearing. Standard library only, read-only.

    python3 audio_probe.py probe FILE.wav [--json] [--cuts 1.2,3.4]

Exit 0 clean, 1 findings, 2 bad input.
"""

from __future__ import annotations

import argparse
import cmath
import json
import math
import os
import struct
import sys
from array import array
from operator import mul
from types import SimpleNamespace

try:
    from math import sumprod as dot
except ImportError:  # Python 3.10 and 3.11

    def dot(a, b):
        return sum(map(mul, a, b))


HOP_MS, MAX_SECONDS, GAP_S, ONSET_DB = 5, 1200, 0.3, 6.0  # block ms, cap, shortest gap listed, onset rise
BRIGHT = (400, 1500, 3500, 6000)  # centroid steps: dark, warm, mid-range, bright, very bright
FFT_N, MAX_FRAMES, TEMPO_BLOCKS = 2048, 64, 24000  # at most 64 frames; tempo reads 120 s from the middle
BANDS = ((20, 150, "bass"), (150, 600, "low_mid"), (600, 2400, "mid"), (2400, 6000, "high_mid"), (6000, 1e9, "high"))
X80, SIGN = bytes(i ^ 128 for i in range(256)), bytes(255 if i > 127 else 0 for i in range(256))
HANN = [0.5 - 0.5 * math.cos(2 * math.pi * i / FFT_N) for i in range(FFT_N)]
TWID = [cmath.exp(-2j * math.pi * k / FFT_N) for k in range(FFT_N // 2)]


class BadInput(Exception):
    """A user mistake or unreadable file: one line, exit 2."""


def pdb(power):
    return 10 * math.log10(power) if power > 1e-12 else -120.0


def parse(f, size):
    """Walk the RIFF chunks; find the format and the samples."""
    if f.read(4) != b"RIFF" or f.read(8)[4:] != b"WAVE":
        raise BadInput("not a RIFF/WAVE file. Convert mp3, ogg, flac or m4a to PCM WAV first")
    fmt, pos = None, 12
    while pos + 8 <= size:
        f.seek(pos)
        cid, csz = struct.unpack("<4sI", f.read(8))
        pos += 8
        if cid == b"fmt ":
            raw = f.read(min(csz, 40))
            if len(raw) < 16:
                raise BadInput("the fmt chunk is cut short")
            tag, ch, rate, _, align, bits = struct.unpack("<HHIIHH", raw[:16])
            tag = struct.unpack("<H", raw[24:26])[0] if tag == 0xFFFE and len(raw) >= 26 else tag
            fmt = (tag, ch, rate, align, bits)
        elif cid == b"data":
            if not fmt:
                raise BadInput("the data chunk comes before the fmt chunk")
            tag, ch, rate, align, bits = fmt
            kind = {1: "int", 3: "float"}.get(tag)
            if kind is None or bits not in ((8, 16, 24, 32) if kind == "int" else (32, 64)):
                raise BadInput(f"format tag {tag} at {bits} bits is not PCM or float WAV. Convert to PCM WAV first")
            if not 1 <= ch <= 8 or not 1000 <= rate <= 768000 or align != ch * bits // 8:
                raise BadInput(f"corrupt or implausible header: {ch} channels, {rate} Hz, block align {align}")
            n, avail = (size - pos if csz == 0xFFFFFFFF else csz), size - pos
            if min(n, avail) < align:
                raise BadInput("the file holds no audio frames")
            return {"kind": kind, "ch": ch, "rate": rate, "align": align, "bits": bits, "off": pos,
                    "frames": min(n, avail) // align, "cut": n > avail or n % align != 0}
        pos += csz + (csz & 1)
    raise BadInput("no data chunk: file cut short or header corrupt" if fmt else "no fmt chunk")


def read(f, w, start, n):
    """Decode n frames from `start` into one array per channel."""
    f.seek(w["off"] + start * w["align"])
    raw = f.read(n * w["align"])
    raw, bits, ch = raw[: len(raw) // w["align"] * w["align"]], w["bits"], w["ch"]
    if w["kind"] == "float":
        a = array("f" if bits == 32 else "d", raw)
    elif bits == 24:
        b = bytearray(len(raw) // 3 * 4)
        b[0::4], b[1::4], b[2::4], b[3::4] = raw[0::3], raw[1::3], raw[2::3], raw[2::3].translate(SIGN)
        a = array("i", b)
    else:
        a = array({8: "b", 16: "h", 32: "i"}[bits], raw.translate(X80) if bits == 8 else raw)
    if sys.byteorder == "big" and bits > 8:
        a.byteswap()
    wide = bits == 32 and w["kind"] == "int"
    return [array("d", a[c::ch]) if wide else a[c::ch] for c in range(ch)]


def scan(f, w, n, hop):
    """One pass: block energy, peak, DC, clipping runs, stereo sum."""
    ch, flt = w["ch"], w["kind"] == "float"
    fs = 1.0 if flt else float(2 ** (w["bits"] - 1))
    hi = 1.0 if flt else fs - 1 - (w["bits"] > 8)
    lo = -hi if flt else -fs + (w["bits"] > 8)
    r = SimpleNamespace(E=[], chan=[0.0] * ch, dc=[0.0] * ch, lr=0.0, peak=0.0, at=0, full=0)
    run, rail, st = [0] * ch, [0] * ch, [0, 0, n]  # run length, rail (+1 top, -1 bottom); runs of 3+, longest, first

    def end_run(c, at):
        k, run[c] = run[c], 0
        if k >= 3:
            st[0], st[1], st[2] = st[0] + 1, max(st[1], k), min(st[2], at - k)

    for s in range(0, n, hop * 200):
        chs = read(f, w, s, min(hop * 200, n - s))
        m = len(chs[0])
        if ch == 2:
            r.lr += dot(chs[0], chs[1])
        acc = [0.0] * -(-m // hop)
        for c, a in enumerate(chs):
            if flt and not math.isfinite(sum(a)):
                raise BadInput("the float samples contain NaN or Inf: the file is corrupt")
            r.dc[c] += sum(a)
            mx, mn = max(a), min(a)
            if max(mx, -mn) > r.peak:
                r.peak, r.at = max(mx, -mn), s + a.index(mx if mx >= -mn else mn)
            hit = mx >= hi or mn <= lo
            if run[c] and not hit:
                end_run(c, s)
                rail[c] = 0
            for i in range(0, m, hop):
                seg = a[i : i + hop]
                acc[i // hop] += (d := dot(seg, seg))
                r.chan[c] += d
                for j, v in enumerate(seg if hit else ()):
                    if (v >= hi) - (v <= lo) != rail[c]:
                        end_run(c, s + i + j)
                        rail[c] = (v >= hi) - (v <= lo)
                    if rail[c]:
                        run[c], r.full = run[c] + 1, r.full + 1
        r.E += [v / (hop * ch) for v in acc]
        if m % hop:
            r.E[-1] *= hop / (m % hop)
    for c in range(ch):
        end_run(c, n)
    r.runs, r.longest, r.first = st
    return r


def gated(E):
    """Mean power of 400 ms blocks, gated at -70 dBFS and -10 dB."""
    m = min(80, len(E))
    keep = [b for b in (sum(E[i : i + m]) / m for i in range(0, len(E) - m + 1, max(1, m // 4))) if b > 1e-7]
    keep = [b for b in keep if b > 0.1 * sum(keep) / len(keep)]
    return round(pdb(sum(keep) / len(keep)), 2) if keep else None


def find_onsets(E, thr):
    """Rise of the next 20 ms of energy over the last 20 ms."""
    n, lim, cur, score = len(E), max(E) * 1e-5, [], []
    for k in range(n):
        c = sum(E[k : k + 4]) / len(E[k : k + 4])
        p = sum(E[max(0, k - 4) : k]) / (k - max(0, k - 4)) if k else 0.0
        s = 10 * math.log10(max(c, 1e-8) / max(p, 1e-8))
        cur.append(c)
        score.append(s if s >= thr and c >= lim else 0.0)
    taken, picked = bytearray(n + 12), []
    for k in sorted((k for k, s in enumerate(score) if s), key=lambda k: (-score[k], -k)):
        if not taken[k]:
            picked.append(k)
            taken[max(0, k - 10) : k + 11] = b"\1" * len(taken[max(0, k - 10) : k + 11])
    return sorted(picked), score, cur


def refine(f, w, k, hop):
    """Frame where the waveform first reaches 10% of its local peak."""
    a0, p0 = max(0, (k - 3) * hop), max(0, (k - 7) * hop)
    seg = read(f, w, a0, 6 * hop)
    before = read(f, w, p0, a0 - p0) if a0 > p0 else []
    peak = max((max(max(a), -min(a)) for a in seg if len(a)), default=0.0)
    old = max((max(max(a), -min(a)) for a in before if len(a)), default=0.0)
    thr = max(0.1 * peak, 1.5 * old)
    hits = [next((i for i, v in enumerate(a) if abs(v) >= thr), None) for a in seg]
    hits = [h for h in hits if h is not None]
    return a0 + min(hits) if hits else k * hop


def tempo(series, hs, onsets):
    """Autocorrelation of the onset curve, 50-220 BPM."""
    x = series
    if len(x) > TEMPO_BLOCKS:
        x = x[len(x) // 2 - TEMPO_BLOCKS // 2 : len(x) // 2 + TEMPO_BLOCKS // 2]
    lo, hi = round(60 / 220 / hs), round(60 / 50 / hs)
    if onsets < 6 or len(x) < 3 * hi:
        return None, 0.0, f"not enough rhythm: {onsets} onsets in {len(series) * hs:.1f} s (needs 6+)"
    for _ in range(2):
        x = [p + 2 * q + r for p, q, r in zip(x, x[1:], x[2:])]
    r = {}
    for lag in range(lo // 2 - 1, hi + 2):
        a, b = x[:-lag], x[lag:]
        d = math.sqrt(dot(a, a) * dot(b, b))
        r[lag] = dot(a, b) / d if d else 0.0
    best = max(range(lo, hi + 1), key=r.get)
    while best // 2 >= lo and r[(h := max(range(best // 2 - 1, best // 2 + 2), key=r.get))] >= 0.6 * r[best]:
        best = h
    base = sum(r[k] for k in range(lo, hi + 1)) / (hi - lo + 1)
    conf = max(0.0, min(1.0, (r[best] - base) / (1 - base))) if base < 1 else 0.0
    if conf < 0.5:
        return None, round(conf, 2), f"not enough rhythm: no steady pulse (confidence {conf:.2f}, needs 0.50)"
    den = r[best - 1] - 2 * r[best] + r[best + 1]
    lag = best + (0.5 * (r[best - 1] - r[best + 1]) / den if den else 0.0)
    return round(60 / (lag * hs), 1), round(conf, 2), "estimate: may be double or half time"


def fft(x):
    n = len(x)
    if n == 1:
        return x
    e, o = fft(x[0::2]), fft(x[1::2])
    t = [TWID[k * (FFT_N // n)] * o[k] for k in range(n // 2)]
    return [e[k] + t[k] for k in range(n // 2)] + [e[k] - t[k] for k in range(n // 2)]


def spectrum(f, w, n, hop, E, rate, first, last):
    """Mean power spectrum of up to MAX_FRAMES Hann frames."""
    N = FFT_N
    k20, r0 = math.ceil(20 * N / rate), max(0, first * hop - N // 2)
    starts = list(range(r0, min(n, (last + 1) * hop + N // 2) - N + 1, N // 2)) or [max(0, min(r0, n - N))]
    en = [sum(E[s // hop : (s + N) // hop + 1]) for s in starts]
    top = max(en) * 1e-3
    starts = [s for s, v in zip(starts, en) if v >= top]
    starts = [starts[i * len(starts) // MAX_FRAMES] for i in range(MAX_FRAMES)] if len(starts) > MAX_FRAMES else starts
    acc, tw, wt, bins = [0.0] * (N // 2 + 1), 0.0, 0.0, []
    for s in starts:
        m = [sum(t) / w["ch"] for t in zip(*read(f, w, s, N))]
        m += [0.0] * (N - len(m))
        mean = sum(m) / N
        p = [abs(v) ** 2 for v in fft([complex((v - mean) * h) for v, h in zip(m, HANN)])[: N // 2 + 1]]
        tot = sum(p[k20:])
        if tot > 0:
            bins.append(p.index(max(p[k20:]), k20))
            acc = [a + b for a, b in zip(acc, p)]
            tw, wt = tw + tot * math.log10(max(p[k20:]) * (N // 2 + 1 - k20) / tot), wt + tot
    total = sum(acc[k20:])
    if total <= 0:
        return None
    i = acc.index(max(acc[k20:]), k20)
    den = acc[i - 1] - 2 * acc[i] + acc[i + 1] if 0 < i < N // 2 else 0
    hz = [k * rate / N for k in range(N // 2 + 1)][k20:]
    share = {nm: round(100 * sum(p for h, p in zip(hz, acc[k20:]) if a <= h < b) / total, 1) for a, b, nm in BANDS}
    t = max(1, len(bins) // 3)
    lo, up = (sorted(x)[len(x) // 2] * rate / N for x in (bins[:t], bins[-t:]))
    return {"centroid_hz": round(sum(h * p for h, p in zip(hz, acc[k20:])) / total, 1), "band_percent": share,
            "peakiness_log10": round(tw / wt, 2), "frames_used": len(starts),
            "sweep_hz": [round(lo), round(up)] if max(lo, up) > 1.5 * min(lo, up) else None,
            "strongest_hz": round((i + (0.5 * (acc[i - 1] - acc[i + 1]) / den if den else 0)) * rate / N, 1)}


def say(res):
    """One line from the numbers: inference, not hearing."""
    ev, sp, tp = res["events"], res.get("spectrum"), res["tempo"]
    a, d = ev["attack_ms"], ev["decay_ms"]
    fade = "" if d is None else f", then fading in {d:.0f} ms"
    if tp["bpm"]:
        parts = [f"{ev['count']} onsets at about {tp['bpm']:.0f} BPM"]
    elif ev["count"] >= 3:
        parts = [f"{ev['count']} separate events"]
    elif a >= 150:
        parts = [f"swell building for {a:.0f} ms{fade}"]
    elif d is None:
        parts = [f"sustained sound, {res['silence']['active_s']:.1f} s"]
    else:
        kind = "short transient" if d <= 600 else "long-tailed transient"
        parts = ["very short click" if d < 40 else f"{kind}, {d:.0f} ms decay"]
    if sp:
        pk, sw = sp["peakiness_log10"], sp["sweep_hz"]
        step = sum(sp["centroid_hz"] >= t for t in BRIGHT)
        parts.append(("dark", "warm", "mid-range", "bright", "very bright")[step])
        hz = f"tone sweeping {sw[0]} to {sw[1]} Hz" if sw else f"tonal near {sp['strongest_hz']:.0f} Hz"
        parts.append(hz if pk >= 2.2 else "noise-like" if pk < 1.8 else "tonal and noisy")
    return ", ".join(parts + ["clipped"] * bool(res["clipping"]["runs"]))


def analyse(path, o):
    if os.path.exists(path) and not os.path.isfile(path):
        raise BadInput(f"{path} is not a regular file")
    try:
        with open(path, "rb") as f:
            return measure(f, os.path.getsize(path), path, o)
    except OSError as e:
        raise BadInput(f"cannot read {path}: {e.strerror or e}") from None


def measure(f, size, path, o):
    w = parse(f, size)
    rate, ch, total, sil = w["rate"], w["ch"], w["frames"], o.silence_db
    fs = 1.0 if w["kind"] == "float" else float(2 ** (w["bits"] - 1))
    n, hop = min(total, int(o.max_seconds * rate)), max(1, round(rate * HOP_MS / 1000))
    hs = hop / rate
    r = scan(f, w, n, hop)
    E = [e / fs**2 for e in r.E]
    loud = [k for k, e in enumerate(E) if pdb(e) >= sil]
    res = {"file": path, "estimates": ["loudness", "tempo", "spectrum", "summary"], "findings": [], "notes": []}

    def flag(kind, msg):
        res["findings"].append({"kind": kind, "message": msg})

    res["format"] = {"sample_rate": rate, "channels": ch, "bit_depth": w["bits"], "sample_format": w["kind"],
                     "duration_s": round(total / rate, 3), "analysed_s": round(n / rate, 3)}
    if n < total:
        res["notes"].append(f"capped: only the first {n / rate:.0f} s of {total / rate:.0f} s were analysed")
    if w["cut"]:
        flag("truncated", "the header promises more audio than the file holds (cut short or corrupt)")
    dc = max(abs(v) for v in r.dc) / n / fs
    pk = round(pdb((r.peak / fs) ** 2), 2)
    rms = round(pdb(math.fsum(r.chan) / (n * ch) / fs**2), 2)
    res["level"] = {"peak_dbfs": pk, "peak_time_s": round(r.at / rate, 4), "rms_dbfs": rms,
                    "dc_offset": round(dc, 5)}
    res["loudness"] = {"active_rms_dbfs": gated(E), "basis": "plain RMS, not LUFS"}
    over = w["kind"] == "float" and r.peak > 1.0
    res["clipping"] = {"runs": r.runs, "longest_run": r.longest, "full_scale_samples": r.full,
                       "first_s": round(r.first / rate, 4) if r.runs else None, "over_full_scale": over}
    if r.runs:
        flag("clipping", f"{r.runs} full-scale runs (longest {r.longest}), first at {r.first / rate:.3f} s")
    if over:
        flag("clipping", f"float peak {pk} dBFS is over full scale and will clip when converted to integer")
    if dc > 0.01:
        flag("dc_offset", f"DC offset {dc * 100:.1f}% of full scale")
    sl = res["silence"] = {"threshold_dbfs": sil, "leading_s": round(n / rate, 3), "trailing_s": 0.0, "active_s": 0.0,
                           "gaps_total": 0, "gaps": []}
    ev = res["events"] = {"count": 0, "onsets_s": [], "attack_ms": None, "decay_ms": None}
    res["tempo"] = {"bpm": None, "confidence": 0.0, "note": "not enough rhythm: no onsets"}
    if not loud:
        flag("silent", f"nothing rises above {sil} dBFS: the file is silent")
    else:
        first, last = loud[0], loud[-1]
        sl["leading_s"] = round(refine(f, w, first, hop) / rate, 4) if first else 0.0
        sl["trailing_s"] = round((n - min(n, (last + 1) * hop)) / rate, 4)
        sl["active_s"] = round((last + 1 - first) * hs, 3)
        gaps = [(k + 1, j) for k, j in zip(loud, loud[1:]) if (j - k - 1) * hs >= GAP_S]
        sl["gaps_total"] = len(gaps)
        sl["gaps"] = [[round(k * hs, 3), round(j * hs, 3)] for k, j in gaps[:10]]
        if gaps:
            res["notes"].append(f"{len(gaps)} silent gap(s) over {GAP_S} s inside the audio: is that intended?")
        picked, series, cur = find_onsets(E, ONSET_DB)
        times = sorted({round(refine(f, w, k, hop) / rate, 4) for k in picked})
        ev["count"], ev["onsets_s"] = len(times), times[:500]
        pb, pk_s = min(r.at // hop, len(cur) - 1), r.at / rate
        start = [t for t in times if t <= pk_s + 0.005] or [sl["leading_s"]]
        ev["attack_ms"] = round(max(0.0, pk_s - start[-1]) * 1000, 1)
        nxt = min((k for k in picked if k > pb + 2), default=len(cur))
        j = next((j for j in range(pb, nxt) if cur[j] <= cur[pb] / 100), None)
        ev["decay_ms"] = None if j is None else float((j - pb) * HOP_MS)
        bpm, conf, why = tempo(series, hs, len(times))
        res["tempo"] = {"bpm": bpm, "confidence": conf, "note": why}
        res["spectrum"] = spectrum(f, w, n, hop, E, rate, first, last)
    res["stereo"] = None
    if ch == 2 and r.chan[0] > 0 and r.chan[1] > 0:
        ll, rr = r.chan
        rho = r.lr / math.sqrt(ll * rr)
        mono = round(pdb((ll + rr + 2 * r.lr) / (2 * (ll + rr))), 2)
        res["stereo"] = {"correlation": round(rho, 3), "mono_change_db": mono}
        if rho < -0.2:
            flag("mono_compat", f"channels partly out of phase (correlation {rho:.2f}): mono sum changes {mono} dB")
    res["sync"] = None
    if o.cuts:
        res["sync"] = {"tolerance_ms": o.tolerance_ms, "pass": True, "cuts": []}
        for c in o.cuts:
            near = min(ev["onsets_s"], key=lambda t: abs(t - c), default=None)
            off = None if near is None or abs(near - c) > 0.5 else round((near - c) * 1000, 1)
            ok = off is not None and abs(off) <= o.tolerance_ms
            res["sync"]["cuts"].append({"cut_s": c, "offset_ms": off, "pass": ok})
            res["sync"]["pass"] &= ok
            if not ok:
                way = "no onset within 500 ms" if off is None else f"{abs(off):.0f} ms {'late' if off > 0 else 'early'}"
                flag("sync", f"cut at {c} s: {way} (tolerance {o.tolerance_ms:g} ms)")
    res["summary"] = say(res) if loud else "silent"
    return res


def fmt(v):
    if isinstance(v, dict):
        return " | ".join(f"{a} {fmt(b)}" for a, b in v.items())
    return "[" + ", ".join(map(fmt, v[:12])) + (" ..." if len(v) > 12 else "") + "]" if isinstance(v, list) else str(v)


def show(res):
    L = [f"audio_probe: {res['file']}"]
    for k in ("format", "level", "loudness", "clipping", "silence", "events", "tempo", "spectrum", "stereo", "sync"):
        if res.get(k):
            L.append(f"{k:9} {fmt(res[k])}" + (" (estimate)" if k in res["estimates"] else ""))
    L.append(f"Sounds like (inferred from measurements, not heard): {res['summary']}")
    L += [f"note: {x}" for x in res["notes"]]
    L += [f"FINDING [{x['kind']}] {x['message']}" for x in res["findings"]] or ["findings: none"]
    return "\n".join(L)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="audio_probe.py")
    p = ap.add_subparsers(dest="cmd", required=True).add_parser("probe")
    p.add_argument("file")
    p.add_argument("--json", action="store_true", help="print JSON")
    p.add_argument("--cuts", default="", help="cut times in s, comma-separated")
    p.add_argument("--tolerance-ms", type=float, default=40.0, help="sync tolerance")
    p.add_argument("--silence-db", type=float, default=-60.0, help="silence level, dBFS")
    p.add_argument("--max-seconds", type=float, default=MAX_SECONDS, help="analysis cap in s")
    o = ap.parse_args(argv)
    try:
        try:
            o.cuts = [float(c) for c in o.cuts.split(",") if c.strip()]
        except ValueError:
            raise BadInput("--cuts takes numbers separated by commas, e.g. 1.2,3.4") from None
        nums = [o.tolerance_ms, o.silence_db, o.max_seconds, *o.cuts]
        bad = not all(map(math.isfinite, nums)) or min([o.tolerance_ms, *o.cuts]) < 0 or o.max_seconds <= 0
        if bad or o.silence_db > 0 or len(o.cuts) > 200:
            raise BadInput("finite values only: tolerance, cuts >= 0; max-seconds > 0; silence-db <= 0; 200 cuts max")
        res = analyse(o.file, o)
    except BadInput as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    print(json.dumps(res, indent=2) if o.json else show(res))
    return 1 if res["findings"] else 0


if __name__ == "__main__":
    sys.stdout.reconfigure(errors="replace")
    sys.exit(main())
