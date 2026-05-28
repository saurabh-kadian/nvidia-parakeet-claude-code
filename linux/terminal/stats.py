#!/usr/bin/env python3
"""
Parakeet telemetry analyser.
Run: python stats.py [--tail]
"""

import json
import os
import sys
import datetime
from collections import defaultdict

TELEMETRY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "telemetry.jsonl")


def load_events():
    if not os.path.exists(TELEMETRY_FILE):
        print(f"No telemetry yet — {TELEMETRY_FILE} does not exist.")
        sys.exit(0)
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


def fmt(seconds: float) -> str:
    return f"{seconds*1000:.0f}ms" if seconds < 1 else f"{seconds:.2f}s"


def percentile(values: list, p: int) -> float:
    if not values:
        return 0
    s = sorted(values)
    idx = int(len(s) * p / 100)
    return s[min(idx, len(s) - 1)]


def report(events: list):
    transcriptions = [e for e in events if e["event"] == "transcription_complete"]
    recordings     = [e for e in events if e["event"] == "recording_end"]
    pastes         = [e for e in events if e["event"] == "paste_result"]
    sessions       = [e for e in events if e["event"] == "session_start"]
    errors         = [e for e in events if e["event"] == "error"]
    skipped        = [e for e in events if e["event"] == "skipped"]

    print("═" * 52)
    print("  Parakeet — Usage Report")
    print("═" * 52)

    # ── Sessions ──────────────────────────────────────────────────────────────
    print(f"\n  Sessions           {len(sessions)}")
    print(f"  Total recordings   {len(recordings)}")
    print(f"  Transcriptions     {len(transcriptions)}")
    if recordings:
        skip_count = len([e for e in skipped if e.get("reason") == "clip_too_short"])
        empty_count = len([e for e in skipped if e.get("reason") == "empty_transcription"])
        print(f"  Skipped (short)    {skip_count}")
        print(f"  Skipped (empty)    {empty_count}")

    # ── Latency ───────────────────────────────────────────────────────────────
    if transcriptions:
        infer  = [e["inference_s"] for e in transcriptions]
        total  = [e["total_latency_s"] for e in transcriptions]
        rec    = [e["duration_s"] for e in recordings if "duration_s" in e]

        print(f"\n{'─'*52}")
        print("  Latency (inference only)")
        print(f"    avg    {fmt(sum(infer)/len(infer))}")
        print(f"    p50    {fmt(percentile(infer, 50))}")
        print(f"    p95    {fmt(percentile(infer, 95))}")
        print(f"    max    {fmt(max(infer))}")

        print("  Latency (F9 release → paste)")
        print(f"    avg    {fmt(sum(total)/len(total))}")
        print(f"    p50    {fmt(percentile(total, 50))}")
        print(f"    p95    {fmt(percentile(total, 95))}")
        print(f"    max    {fmt(max(total))}")

        if rec:
            print(f"\n  Recording duration")
            print(f"    avg    {fmt(sum(rec)/len(rec))}")
            print(f"    min    {fmt(min(rec))}")
            print(f"    max    {fmt(max(rec))}")

    # ── Output ────────────────────────────────────────────────────────────────
    if transcriptions:
        words  = [e["word_count"] for e in transcriptions]
        total_words = sum(words)
        print(f"\n{'─'*52}")
        print(f"  Words transcribed  {total_words}")
        print(f"  Avg per recording  {total_words/len(transcriptions):.1f} words")
        print(f"  Corrections fired  {sum(e.get('corrections_applied',0) for e in transcriptions)}")

    # ── GPU ───────────────────────────────────────────────────────────────────
    if transcriptions and transcriptions[0].get("gpu_mem_used_mb", 0) > 0:
        mem = [e["gpu_mem_used_mb"] for e in transcriptions]
        print(f"\n{'─'*52}")
        print(f"  GPU memory (used during inference)")
        print(f"    avg    {sum(mem)/len(mem):.0f} MB")
        print(f"    max    {max(mem):.0f} MB")
        res = [e["gpu_mem_reserved_mb"] for e in transcriptions]
        print(f"    reserved (peak)  {max(res):.0f} MB")

    # ── Paste success rate ────────────────────────────────────────────────────
    if pastes:
        ok = sum(1 for e in pastes if e["exit_code"] == 0)
        print(f"\n{'─'*52}")
        print(f"  Paste success      {ok}/{len(pastes)} ({100*ok//len(pastes)}%)")

    # ── Errors ────────────────────────────────────────────────────────────────
    if errors:
        print(f"\n{'─'*52}")
        print(f"  Errors             {len(errors)}")
        by_stage = defaultdict(list)
        for e in errors:
            by_stage[e.get("stage", "unknown")].append(e.get("message", ""))
        for stage, msgs in by_stage.items():
            print(f"    {stage}: {len(msgs)}x  (last: {msgs[-1][:60]})")

    # ── Usage by hour ─────────────────────────────────────────────────────────
    if recordings:
        by_hour = defaultdict(int)
        for e in recordings:
            hour = datetime.datetime.fromtimestamp(e["ts"]).hour
            by_hour[hour] += 1
        print(f"\n{'─'*52}")
        print("  Usage by hour (local time)")
        for h in sorted(by_hour):
            bar = "█" * by_hour[h]
            print(f"    {h:02d}:00  {bar} {by_hour[h]}")

    print(f"\n{'═'*52}")
    print(f"  Log: {TELEMETRY_FILE}")
    print("═" * 52)


if __name__ == "__main__":
    if "--tail" in sys.argv:
        import time
        print("Watching telemetry (Ctrl+C to stop)...\n")
        seen = 0
        while True:
            events = load_events()
            for e in events[seen:]:
                ts = datetime.datetime.fromtimestamp(e["ts"]).strftime("%H:%M:%S")
                if e["event"] == "transcription_complete":
                    print(f"  {ts}  infer={fmt(e['inference_s'])}  total={fmt(e['total_latency_s'])}  words={e['word_count']}  gpu={e['gpu_mem_used_mb']:.0f}MB")
                elif e["event"] in ("error", "skipped"):
                    print(f"  {ts}  {e['event']}: {e.get('reason') or e.get('message')}")
            seen = len(events)
            time.sleep(1)
    else:
        report(load_events())
