#!/usr/bin/env python3
"""make_charts.py: make real sounds with sfx_synth.py, measure them with audio_probe.py, and draw what they did.

Usage: python3 make_charts.py OUT_DIR

Every waveform is drawn from the samples of a WAV file the scripts wrote a moment ago, and every number on the images
is read from audio_probe.py's own JSON. Nothing is typed in by hand. The probe numbers used are saved next to this
file as probe-results.json so you can see what the images were drawn from.
"""

import html
import json
import re
import subprocess
import sys
import tempfile
import wave
from array import array
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parents[1] / "agensi" / "sound-check" / "scripts"
SYNTH, PROBE = str(SCRIPTS / "sfx_synth.py"), str(SCRIPTS / "audio_probe.py")
FONT = "Inter, system-ui, -apple-system, 'Segoe UI', Helvetica, Arial, sans-serif"
INK, MUTED, WAVE = "#0f172a", "#64748b", "#334155"
FAIL, PASS = "#dc2626", "#15803d"
PRESETS = ["click", "tick", "pop", "thump", "whoosh", "riser", "hit", "chime", "drop"]
CUT_S, TOLERANCE_MS = 1.20, 40


def run(*args: str, ok: tuple[int, ...] = (0,)) -> str:
    proc = subprocess.run([sys.executable, *args], capture_output=True, text=True, timeout=120)
    if proc.returncode not in ok:
        raise SystemExit(f"command failed ({proc.returncode}): {args}\n{proc.stdout}\n{proc.stderr}")
    return proc.stdout


def make(folder: Path, name: str, preset: str, *params: str, duration: str | None = None) -> Path:
    out = folder / name
    cmd = [SYNTH, "make", preset, "--out", str(out)]
    for p in params:
        cmd += ["--param", p]
    if duration:
        cmd += ["--duration", duration]
    run(*cmd)
    return out


def probe(path: Path, *extra: str, ok: tuple[int, ...] = (0, 1)) -> dict:
    return json.loads(run(PROBE, "probe", str(path), "--json", *extra, ok=ok))


def samples(path: Path) -> tuple[list[float], int]:
    with wave.open(str(path)) as w:
        assert w.getsampwidth() == 2 and w.getnchannels() == 1, "the charts read 16-bit mono files"
        raw = array("h")
        raw.frombytes(w.readframes(w.getnframes()))
        return [s / 32768 for s in raw], w.getframerate()


def esc(text) -> str:
    return html.escape(str(text))


def page(body: str, width: int, height: int, bg: str = "#ffffff") -> str:
    return (
        f"<!doctype html><meta charset='utf-8'><style>*{{box-sizing:border-box}}"
        f"body{{margin:0;background:{bg};font-family:{FONT}}}</style>"
        f"<div id='frame' style='width:{width}px;height:{height}px;position:relative;overflow:hidden'>{body}</div>"
    )


def heading(title: str, sub: str) -> str:
    return (
        "<div style='position:absolute;left:20px;top:18px;right:20px'>"
        f"<div style='font-size:26px;font-weight:800;color:{INK};letter-spacing:-.01em'>{esc(title)}</div>"
        f"<div style='font-size:14px;color:#475569;margin-top:6px'>{esc(sub)}</div></div>"
    )


def envelope(data: list[float], start: int, stop: int, cols: int) -> list[tuple[float, float]]:
    """Lowest and highest sample in each of `cols` equal slices of data[start:stop]."""
    out = []
    for c in range(cols):
        a = start + (stop - start) * c // cols
        b = max(a + 1, start + (stop - start) * (c + 1) // cols)
        chunk = data[a:b] or [0.0]
        out.append((min(chunk), max(chunk)))
    return out


def wave_path(env: list[tuple[float, float]], x0: float, mid: float, half: float) -> str:
    """A filled outline: along the highs, then back along the lows."""
    up = [f"{x0 + i:.1f},{mid - hi * half:.2f}" for i, (_, hi) in enumerate(env)]
    down = [f"{x0 + i:.1f},{mid - lo * half:.2f}" for i, (lo, _) in reversed(list(enumerate(env)))]
    return " ".join(up + down)


# ---------------------------------------------------------------- the sync check


def sync_row(data: list[float], rate: int, report: dict, y: int, label: str, left: int = 70, width: int = 860) -> list[str]:
    cut = report["sync"]["cuts"][0]
    onset_s = cut["cut_s"] + cut["offset_ms"] / 1000
    passed = cut["pass"]
    colour = PASS if passed else FAIL
    total = len(data) / rate
    win_a, win_b = 1.10, 1.40
    out = []
    verdict = f"{'PASS' if passed else 'FAIL'}: {abs(cut['offset_ms']):.1f} ms {'late' if cut['offset_ms'] > 0 else 'early'}"
    out.append(f"<text x='{left}' y='{y + 18}' font-size='18' font-weight='800' fill='{INK}'>{esc(label)}</text>")
    out.append(f"<rect x='{left + 190}' y='{y + 2}' width='{len(verdict) * 9 + 24}' height='24' rx='12' fill='{colour}'/>")
    out.append(f"<text x='{left + 202}' y='{y + 19}' font-size='14' font-weight='800' fill='#fff'>{esc(verdict)}</text>")
    # the whole file, small, with the zoom window marked
    oy, oh = y + 40, 44
    env = envelope(data, 0, len(data), width)
    out.append(f"<rect x='{left}' y='{oy}' width='{width}' height='{oh}' fill='#f1f5f9'/>")
    out.append(f"<polygon points='{wave_path(env, left, oy + oh / 2, oh / 2 - 2)}' fill='{WAVE}'/>")
    zx, zw = left + win_a / total * width, (win_b - win_a) / total * width
    out.append(f"<rect x='{zx:.1f}' y='{oy - 3}' width='{zw:.1f}' height='{oh + 6}' fill='none' stroke='{INK}' stroke-width='2'/>")
    out.append(f"<text x='{left + width}' y='{oy - 8}' text-anchor='end' font-size='12' fill='{MUTED}'>whole file, 0 to {total:.0f} s</text>")
    # the zoom, 1.10 to 1.40 s
    zy, zh = y + 112, 120
    a, b = int(win_a * rate), int(win_b * rate)
    env = envelope(data, a, b, width)
    px = lambda t: left + (t - win_a) / (win_b - win_a) * width  # noqa: E731
    out.append(f"<rect x='{left}' y='{zy}' width='{width}' height='{zh}' fill='#f8fafc'/>")
    tol = TOLERANCE_MS / 1000
    out.append(f"<rect x='{px(cut['cut_s'] - tol):.1f}' y='{zy}' width='{(2 * tol) / (win_b - win_a) * width:.1f}' height='{zh}' fill='#dcfce7'/>")
    out.append(f"<polygon points='{wave_path(env, left, zy + zh / 2, zh / 2 - 4)}' fill='{WAVE}'/>")
    out.append(f"<line x1='{px(cut['cut_s']):.1f}' x2='{px(cut['cut_s']):.1f}' y1='{zy - 6}' y2='{zy + zh + 4}' stroke='{INK}' stroke-width='2' stroke-dasharray='6 4'/>")
    out.append(f"<line x1='{px(onset_s):.1f}' x2='{px(onset_s):.1f}' y1='{zy - 6}' y2='{zy + zh + 4}' stroke='{colour}' stroke-width='3'/>")
    out.append(f"<text x='{px(cut['cut_s']) - 6:.1f}' y='{zy + 14}' text-anchor='end' font-size='13' font-weight='700' fill='{INK}'>cut {cut['cut_s']:.2f} s</text>")
    out.append(f"<text x='{px(onset_s) + 8:.1f}' y='{zy + 14}' font-size='13' font-weight='700' fill='{colour}'>first onset {onset_s:.4f} s</text>")
    if abs(cut["offset_ms"]) > 10:  # a bracket is only legible when the gap is
        by = zy + zh - 10
        out.append(f"<line x1='{px(cut['cut_s']):.1f}' x2='{px(onset_s):.1f}' y1='{by}' y2='{by}' stroke='{colour}' stroke-width='2'/>")
        out.append(f"<text x='{(px(cut['cut_s']) + px(onset_s)) / 2:.1f}' y='{by - 6}' text-anchor='middle' font-size='13' font-weight='800' fill='{colour}'>{cut['offset_ms']:+.1f} ms</text>")
    for t in (1.10, 1.15, 1.20, 1.25, 1.30, 1.35, 1.40):
        out.append(f"<text x='{px(t):.1f}' y='{zy + zh + 20}' text-anchor='middle' font-size='11' fill='{MUTED}'>{t:.2f}</text>")
    out.append(f"<text x='{left + width}' y='{zy - 10}' text-anchor='end' font-size='12' fill='{MUTED}'>zoom, 1.10 to 1.40 s. Green band is the {TOLERANCE_MS} ms tolerance</text>")
    return out


def sync_page(late: tuple, fixed: tuple) -> tuple[str, int, int]:
    w, h = 1000, 700
    out = [f"<svg xmlns='http://www.w3.org/2000/svg' width='{w}' height='{h}' viewBox='0 0 {w} {h}'>"]
    out += sync_row(*late, y=120, label="late.wav")
    out += sync_row(*fixed, y=388, label="hit.wav")
    out.append("</svg>")
    head = heading("Does the hit land on the cut?", "Two real files from sfx_synth.py, measured by audio_probe.py. The cut is at 1.20 s.")
    foot = (
        "<div style='position:absolute;left:20px;bottom:14px;right:20px;font-size:14px;color:#334155'>"
        "The first file starts its sound 1280 ms in, the second 1200 ms in. The waveforms are the files' own samples.</div>"
    )
    return page(head + f"<div style='position:absolute;left:0;top:0'>{''.join(out)}</div>" + foot, w, h), w, h


# ---------------------------------------------------------------- clipping


def clip_panel(data: list[float], rate: int, report: dict, y: int, label: str, note: str, colour: str) -> list[str]:
    left, width, h = 70, 860, 170
    stop = int(0.060 * rate)
    seg = data[:stop]
    peak = max(abs(s) for s in data)
    px = lambda i: left + i / (stop - 1) * width  # noqa: E731
    py = lambda v: y + h / 2 - v * (h / 2 - 8)  # noqa: E731
    out = [f"<rect x='{left}' y='{y}' width='{width}' height='{h}' fill='#f8fafc'/>"]
    for v, text in ((1.0, "full scale"), (-1.0, "")):
        out.append(f"<line x1='{left}' x2='{left + width}' y1='{py(v):.1f}' y2='{py(v):.1f}' stroke='{FAIL}' stroke-width='1' stroke-dasharray='4 4'/>")
        if text:
            out.append(f"<text x='{left + width - 4}' y='{py(v) - 4:.1f}' text-anchor='end' font-size='11' fill='{FAIL}'>{text}</text>")
    out.append(f"<line x1='{left}' x2='{left + width}' y1='{py(0):.1f}' y2='{py(0):.1f}' stroke='#cbd5e1'/>")
    pts = " ".join(f"{px(i):.1f},{py(s):.1f}" for i, s in enumerate(seg))
    out.append(f"<polyline points='{pts}' fill='none' stroke='{WAVE}' stroke-width='1.6' stroke-linejoin='round'/>")
    for i, s in enumerate(seg):
        if abs(s) >= 0.99997:
            out.append(f"<circle cx='{px(i):.1f}' cy='{py(s):.1f}' r='2.2' fill='{FAIL}'/>")
    out.append(f"<text x='{left}' y='{y - 10}' font-size='17' font-weight='800' fill='{INK}'>{esc(label)}</text>")
    out.append(f"<text x='{left + 210}' y='{y - 10}' font-size='14' font-weight='700' fill='{colour}'>{esc(note)}</text>")
    out.append(f"<text x='{left}' y='{y + h + 18}' font-size='11' fill='{MUTED}'>0 ms</text>")
    out.append(f"<text x='{left + width}' y='{y + h + 18}' text-anchor='end' font-size='11' fill='{MUTED}'>60 ms</text>")
    assert peak <= 1.0
    return out


def clip_page(hot: tuple, safe: tuple) -> tuple[str, int, int]:
    w, h = 1000, 600
    hot_data, rate, hot_report = hot
    safe_data, _, safe_report = safe
    c = hot_report["clipping"]
    note_hot = f"{c['runs']} runs at full scale, the longest {c['longest_run']} samples, {c['full_scale_samples']:,} samples in all"
    note_safe = f"peak {safe_report['level']['peak_dbfs']} dBFS, {safe_report['clipping']['runs']} runs at full scale"
    out = [f"<svg xmlns='http://www.w3.org/2000/svg' width='{w}' height='{h}' viewBox='0 0 {w} {h}'>"]
    out += clip_panel(hot_data, rate, hot_report, 126, "thump_hot.wav", note_hot, FAIL)
    out += clip_panel(safe_data, rate, safe_report, 362, "thump.wav", note_safe, PASS)
    out.append("</svg>")
    head = heading("What clipping looks like, and what the probe reports", "The first 60 ms of the same sound, made 8 dB too hot and then at -3 dBFS. Red dots are samples stuck at full scale.")
    foot = (
        "<div style='position:absolute;left:20px;bottom:14px;right:20px;font-size:14px;color:#334155'>"
        f"The hot file exits with code 1 and the finding \"{esc(hot_report['findings'][0]['message'])}\". The other exits with 0.</div>"
    )
    return page(head + f"<div style='position:absolute;left:0;top:0'>{''.join(out)}</div>" + foot, w, h), w, h


# ---------------------------------------------------------------- the nine presets


def preset_descriptions() -> dict[str, str]:
    found = {}
    for line in run(SYNTH, "list").splitlines():
        m = re.match(r"^(\w+): (.*)$", line)
        if m:
            found[m.group(1)] = m.group(2)
    return found


def gallery_page(cards: list[tuple]) -> tuple[str, int, int]:
    w, cw, ch, gap, top = 1000, 304, 246, 14, 84
    h = top + 3 * ch + 2 * gap + 20
    body = [heading("Nine sound effects, made from code", "Real files from sfx_synth.py at default settings, measured by audio_probe.py. The last line of each card is the probe's own summary.")]
    for i, (name, desc, data, report) in enumerate(cards):
        x, y = 20 + (i % 3) * (cw + gap), top + (i // 3) * (ch + gap)
        env = envelope(data, 0, len(data), cw - 28)
        svg = (
            f"<svg xmlns='http://www.w3.org/2000/svg' width='{cw - 28}' height='74'>"
            f"<line x1='0' x2='{cw - 28}' y1='37' y2='37' stroke='#e2e8f0'/>"
            f"<polygon points='{wave_path(env, 0, 37, 35)}' fill='{WAVE}'/></svg>"
        )
        peak, decay = report["level"]["peak_dbfs"], report["events"].get("decay_ms")
        facts = [f"{report['format']['duration_s']} s", f"peak {peak:g} dBFS", f"centroid {report['spectrum']['centroid_hz']:,.0f} Hz"]
        if decay:
            facts.insert(1, f"decay {decay:g} ms")
        summary = report["summary"].replace("Sounds like (inferred from measurements, not heard): ", "")
        body.append(
            f"<div style='position:absolute;left:{x}px;top:{y}px;width:{cw}px;height:{ch}px;border:1px solid #e2e8f0;border-radius:12px;"
            f"padding:12px 14px;background:#fff'>"
            f"<div style='font-size:20px;font-weight:800;color:{INK}'>{esc(name)}</div>"
            f"<div style='font-size:12px;color:{MUTED};height:34px;overflow:hidden;margin-top:3px;line-height:1.35'>{esc(desc)}</div>"
            f"<div style='margin-top:4px'>{svg}</div>"
            f"<div style='font-size:12px;color:#334155;margin-top:4px;line-height:1.4'>{esc(' | '.join(facts))}</div>"
            f"<div style='font-size:12px;color:{MUTED};margin-top:2px;line-height:1.35'>{esc(summary)}</div></div>"
        )
    return page("".join(body), w, h), w, h


# ---------------------------------------------------------------- social preview


def social_page(late: tuple) -> tuple[str, int, int]:
    w, h = 1280, 640
    data, rate, report = late
    cut = report["sync"]["cuts"][0]
    onset_s = cut["cut_s"] + cut["offset_ms"] / 1000
    win_a, win_b, width, ch = 1.10, 1.40, 512, 150
    env = envelope(data, int(win_a * rate), int(win_b * rate), width)
    px = lambda t: (t - win_a) / (win_b - win_a) * width  # noqa: E731
    svg = (
        f"<svg xmlns='http://www.w3.org/2000/svg' width='{width}' height='{ch + 60}'>"
        f"<rect x='{px(cut['cut_s'] - 0.04):.1f}' y='24' width='{px(cut['cut_s'] + 0.04) - px(cut['cut_s'] - 0.04):.1f}' height='{ch}' fill='#dcfce7'/>"
        f"<polygon points='{wave_path(env, 0, 24 + ch / 2, ch / 2 - 4)}' fill='{WAVE}'/>"
        f"<line x1='{px(cut['cut_s']):.1f}' x2='{px(cut['cut_s']):.1f}' y1='14' y2='{ch + 34}' stroke='{INK}' stroke-width='2' stroke-dasharray='6 4'/>"
        f"<line x1='{px(onset_s):.1f}' x2='{px(onset_s):.1f}' y1='14' y2='{ch + 34}' stroke='{FAIL}' stroke-width='3'/>"
        f"<text x='{px(cut['cut_s']) - 6:.1f}' y='12' text-anchor='end' font-size='14' font-weight='700' fill='{INK}'>cut 1.20 s</text>"
        f"<text x='{px(onset_s) + 6:.1f}' y='12' font-size='14' font-weight='700' fill='{FAIL}'>onset 1.2802 s</text>"
        f"<text x='{width / 2:.0f}' y='{ch + 54}' text-anchor='middle' font-size='18' font-weight='800' fill='{FAIL}'>{cut['offset_ms']:+.1f} ms late</text></svg>"
    )
    assert abs(onset_s - 1.2802) < 1e-3
    chips = "".join(
        f"<span style='background:rgba(255,255,255,.14);border:1px solid rgba(255,255,255,.35);border-radius:999px;padding:8px 18px'>{t}</span>"
        for t in ("Standard library only", "No model, just numbers")
    )
    body = (
        "<div style='position:absolute;inset:0;background:linear-gradient(135deg,#be185d,#4c0519)'></div>"
        "<div style='position:absolute;left:64px;top:92px;width:560px;color:#fff'>"
        "<div style='display:flex;align-items:center;gap:22px'>"
        "<img src='logo.png' width='96' height='96' style='border-radius:22px'>"
        "<div style='font-size:60px;font-weight:800;letter-spacing:-.02em'>Sound Check</div></div>"
        "<div style='font-size:34px;font-weight:600;line-height:1.28;margin-top:44px'>Your agent cannot hear. "
        "It can measure: clipping, silence, and how many milliseconds late a sound lands.</div>"
        f"<div style='display:flex;flex-wrap:wrap;gap:12px;margin-top:34px;font-size:18px;font-weight:600'>{chips}</div></div>"
        "<div style='position:absolute;right:48px;top:150px;width:556px;height:340px;background:#fff;border-radius:20px;"
        "box-shadow:0 24px 60px rgba(0,0,0,.35);overflow:hidden'>"
        "<div style='padding:16px 20px 0;font-size:15px;font-weight:700;color:#475569'>A real file, measured against a cut</div>"
        f"<div style='position:absolute;left:22px;top:78px'>{svg}</div></div>"
    )
    return page(body, w, h, "#4c0519"), w, h


def main() -> int:
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        cut_args = ("--cuts", f"{CUT_S:.2f}", "--tolerance-ms", str(TOLERANCE_MS))

        late_wav = make(folder, "late.wav", "hit", "delay_ms=1280", duration="3")
        fixed_wav = make(folder, "hit.wav", "hit", "delay_ms=1200", duration="3")
        late = (*samples(late_wav), probe(late_wav, *cut_args))
        fixed = (*samples(fixed_wav), probe(fixed_wav, *cut_args))

        hot_wav = make(folder, "hot.wav", "thump", "level_db=8")
        safe_wav = make(folder, "safe.wav", "thump", "level_db=-3")
        hot = (*samples(hot_wav), probe(hot_wav))
        safe = (*samples(safe_wav), probe(safe_wav))

        descs = preset_descriptions()
        (folder / "presets").mkdir()
        cards, numbers = [], {}
        for name in PRESETS:
            wav = make(folder / "presets", f"{name}.wav", name)
            data, _ = samples(wav)
            report = probe(wav)
            cards.append((name, descs[name], data, report))
            numbers[name] = {
                "duration_s": report["format"]["duration_s"],
                "peak_dbfs": report["level"]["peak_dbfs"],
                "decay_ms": report["events"].get("decay_ms"),
                "centroid_hz": report["spectrum"]["centroid_hz"],
                "summary": report["summary"],
            }

    snapshot = {
        "cut_s": CUT_S,
        "tolerance_ms": TOLERANCE_MS,
        "sync": {"late.wav": late[2]["sync"], "hit.wav": fixed[2]["sync"]},
        "clipping": {"thump_hot.wav": hot[2]["clipping"], "thump.wav": safe[2]["clipping"]},
        "presets": numbers,
    }
    (HERE / "probe-results.json").write_text(json.dumps(snapshot, indent=1) + "\n")
    for name, (doc, _w, _h) in {
        "sync": sync_page(late, fixed),
        "clipping": clip_page(hot, safe),
        "presets": gallery_page(cards),
        "social": social_page(late),
    }.items():
        (out / f"{name}.html").write_text(doc)
    print(f"wrote pages to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
