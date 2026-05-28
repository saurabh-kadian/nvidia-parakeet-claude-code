"""Telemetry analyser — identical to Linux version."""

import json, datetime
from collections import defaultdict
from .config import TELEMETRY_FILE


def load_events() -> list:
    if not TELEMETRY_FILE.exists():
        return []
    events = []
    with open(TELEMETRY_FILE) as f:
        for line in f:
            line = line.strip()
            if line:
                try:    events.append(json.loads(line))
                except: pass
    return events


def _fmt(s): return f"{s*1000:.0f}ms" if s < 1 else f"{s:.2f}s"
def _pct(v, p): return sorted(v)[min(int(len(v)*p/100), len(v)-1)] if v else 0


def report(events: list) -> str:
    tr  = [e for e in events if e["event"] == "transcription_complete"]
    rec = [e for e in events if e["event"] == "recording_end"]
    pas = [e for e in events if e["event"] == "paste_result"]
    ses = [e for e in events if e["event"] == "session_start"]
    err = [e for e in events if e["event"] == "error"]
    skp = [e for e in events if e["event"] == "skipped"]

    lines = []
    w = lines.append
    w("=" * 52)
    w("  Parakeet PTT — Usage Report")
    w("=" * 52)
    w(f"\n  Sessions           {len(ses)}")
    w(f"  Total recordings   {len(rec)}")
    w(f"  Transcriptions     {len(tr)}")
    if rec:
        w(f"  Skipped (short)    {sum(1 for e in skp if e.get('reason')=='clip_too_short')}")
        w(f"  Skipped (empty)    {sum(1 for e in skp if e.get('reason')=='empty_transcription')}")

    if tr:
        infer = [e["inference_s"]     for e in tr]
        total = [e["total_latency_s"] for e in tr]
        dur   = [e["duration_s"]      for e in rec if "duration_s" in e]
        w(f"\n{'-'*52}")
        w(f"  Inference   avg {_fmt(sum(infer)/len(infer))}  p50 {_fmt(_pct(infer,50))}  p95 {_fmt(_pct(infer,95))}  max {_fmt(max(infer))}")
        w(f"  Total       avg {_fmt(sum(total)/len(total))}  p50 {_fmt(_pct(total,50))}  p95 {_fmt(_pct(total,95))}  max {_fmt(max(total))}")
        if dur:
            w(f"  Recording   avg {_fmt(sum(dur)/len(dur))}  min {_fmt(min(dur))}  max {_fmt(max(dur))}")
        words = sum(e["word_count"] for e in tr)
        w(f"\n  Words transcribed  {words}  (avg {words/len(tr):.1f} / recording)")
        w(f"  Corrections fired  {sum(e.get('corrections_applied',0) for e in tr)}")
        mem = [e["gpu_mem_used_mb"] for e in tr if e.get("gpu_mem_used_mb",0)>0]
        if mem:
            res = [e["gpu_mem_reserved_mb"] for e in tr if e.get("gpu_mem_used_mb",0)>0]
            w(f"  GPU memory  avg {sum(mem)/len(mem):.0f} MB  max {max(mem):.0f} MB  reserved {max(res):.0f} MB")

    if pas:
        ok = sum(1 for e in pas if e["exit_code"]==0)
        w(f"\n  Paste success  {ok}/{len(pas)} ({100*ok//len(pas)}%)")

    if err:
        by: dict = defaultdict(list)
        for e in err: by[e.get("stage","?")].append(e.get("message",""))
        w(f"\n  Errors  {len(err)}")
        for stage, msgs in by.items():
            w(f"    {stage}: {len(msgs)}×  last: {msgs[-1][:60]}")

    if rec:
        by_h: dict = defaultdict(int)
        for e in rec: by_h[datetime.datetime.fromtimestamp(e["ts"]).hour] += 1
        w(f"\n  Usage by hour")
        for h in sorted(by_h): w(f"    {h:02d}:00  {'█'*by_h[h]} {by_h[h]}")

    w(f"\n{'='*52}")
    return "\n".join(lines)
