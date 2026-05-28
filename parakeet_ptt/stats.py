"""
Telemetry analyser — shared between the stats window and the CLI.
"""

import json
import datetime
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
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return events


def _fmt(seconds: float) -> str:
    return f"{seconds*1000:.0f}ms" if seconds < 1 else f"{seconds:.2f}s"


def _pct(values: list, p: int) -> float:
    if not values:
        return 0
    s = sorted(values)
    return s[min(int(len(s) * p / 100), len(s) - 1)]


def report(events: list) -> str:
    transcriptions = [e for e in events if e["event"] == "transcription_complete"]
    recordings     = [e for e in events if e["event"] == "recording_end"]
    pastes         = [e for e in events if e["event"] == "paste_result"]
    sessions       = [e for e in events if e["event"] == "session_start"]
    errors         = [e for e in events if e["event"] == "error"]
    skipped        = [e for e in events if e["event"] == "skipped"]

    lines = []
    w = lines.append

    w("=" * 52)
    w("  Parakeet PTT — Usage Report")
    w("=" * 52)
    w(f"\n  Sessions           {len(sessions)}")
    w(f"  Total recordings   {len(recordings)}")
    w(f"  Transcriptions     {len(transcriptions)}")
    if recordings:
        w(f"  Skipped (short)    {sum(1 for e in skipped if e.get('reason') == 'clip_too_short')}")
        w(f"  Skipped (empty)    {sum(1 for e in skipped if e.get('reason') == 'empty_transcription')}")

    if transcriptions:
        infer = [e["inference_s"]      for e in transcriptions]
        total = [e["total_latency_s"]  for e in transcriptions]
        rec   = [e["duration_s"]       for e in recordings if "duration_s" in e]

        w(f"\n{'-'*52}")
        w("  Inference latency")
        w(f"    avg  {_fmt(sum(infer)/len(infer))}   p50  {_fmt(_pct(infer,50))}   p95  {_fmt(_pct(infer,95))}   max  {_fmt(max(infer))}")
        w("  Total latency (key release → paste)")
        w(f"    avg  {_fmt(sum(total)/len(total))}   p50  {_fmt(_pct(total,50))}   p95  {_fmt(_pct(total,95))}   max  {_fmt(max(total))}")

        if rec:
            w(f"\n  Recording duration")
            w(f"    avg  {_fmt(sum(rec)/len(rec))}   min  {_fmt(min(rec))}   max  {_fmt(max(rec))}")

        words = [e["word_count"] for e in transcriptions]
        total_words = sum(words)
        w(f"\n{'-'*52}")
        w(f"  Words transcribed  {total_words}  (avg {total_words/len(transcriptions):.1f} / recording)")
        w(f"  Corrections fired  {sum(e.get('corrections_applied',0) for e in transcriptions)}")

        mem = [e["gpu_mem_used_mb"] for e in transcriptions if e.get("gpu_mem_used_mb", 0) > 0]
        if mem:
            res = [e["gpu_mem_reserved_mb"] for e in transcriptions if e.get("gpu_mem_used_mb", 0) > 0]
            w(f"\n{'-'*52}")
            w(f"  GPU memory  avg {sum(mem)/len(mem):.0f} MB   max {max(mem):.0f} MB   reserved (peak) {max(res):.0f} MB")

    if pastes:
        ok = sum(1 for e in pastes if e["exit_code"] == 0)
        w(f"\n{'-'*52}")
        w(f"  Paste success  {ok}/{len(pastes)} ({100*ok//len(pastes)}%)")

    if errors:
        w(f"\n{'-'*52}")
        w(f"  Errors  {len(errors)}")
        by_stage: dict = defaultdict(list)
        for e in errors:
            by_stage[e.get("stage", "unknown")].append(e.get("message", ""))
        for stage, msgs in by_stage.items():
            w(f"    {stage}: {len(msgs)}×  last: {msgs[-1][:60]}")

    if recordings:
        by_hour: dict = defaultdict(int)
        for e in recordings:
            by_hour[datetime.datetime.fromtimestamp(e["ts"]).hour] += 1
        w(f"\n{'-'*52}")
        w("  Usage by hour (local time)")
        for h in sorted(by_hour):
            w(f"    {h:02d}:00  {'█' * by_hour[h]} {by_hour[h]}")

    w(f"\n{'='*52}")
    return "\n".join(lines)
