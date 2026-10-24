"""
Run every bundled sample through the live API and print the numbers the demo claims:
urgency, level, named script, fraud/distress components and per-window latency.

  python eval.py            # expects the API on 127.0.0.1:8765
  python eval.py --json     # machine-readable

Expected ordering (by design, not by tuning on these clips): fraudster + victim scripts should land
medium/high/critical; the control 'normal-query' should stay low. Anything else is a bug to fix.
"""
import json
import sys
import time
import urllib.request
from pathlib import Path

API = "http://127.0.0.1:8765"
SAMPLES = Path(__file__).resolve().parent.parent / "samples"


def post_file(path: Path) -> dict:
    boundary = "----awaaz"
    body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{path.name}\"\r\n"
            f"Content-Type: audio/wav\r\n\r\n").encode() + path.read_bytes() + f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(f"{API}/analyze", data=body, headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    with urllib.request.urlopen(req, timeout=600) as r:
        return json.loads(r.read())


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    meta = json.loads((SAMPLES / "samples.json").read_text(encoding="utf-8"))
    rows = []
    for s in meta:
        t0 = time.perf_counter()
        res = post_file(SAMPLES / s["file"])
        wall = time.perf_counter() - t0
        o = res["overall"]
        w = res["windows"]
        rows.append({
            "id": s["id"], "kind": s["kind"], "duration_s": res["duration"],
            "urgency": o["urgency"], "level": o["level"], "signature": o["signature"],
            "max_fraud": round(max(x["fraud"]["score"] for x in w), 2),
            "max_distress": round(max(x["distress"] for x in w), 2),
            "avg_latency_ms": o["avg_latency_ms"], "wall_s": round(wall, 1),
            "realtime_factor": round(wall / max(0.1, res["duration"]), 2),
            "lang": max(set(x["language"] for x in w if x["language"]), key=[x["language"] for x in w].count) if any(x["language"] for x in w) else None,
            "explain": o["explain"][:3],
        })
    if "--json" in sys.argv:
        print(json.dumps(rows, ensure_ascii=False, indent=2)); return
    print(f"{'sample':<17}{'kind':<11}{'dur':>5} {'urg':>4} {'level':<9}{'script':<24}{'fraud':>6}{'distr':>6}{'lat ms':>7}{'RTF':>5}  lang")
    for r in rows:
        print(f"{r['id']:<17}{r['kind']:<11}{r['duration_s']:>5.0f} {r['urgency']:>4} {r['level']:<9}{str(r['signature'] or '-'):<24}{r['max_fraud']:>6}{r['max_distress']:>6}{r['avg_latency_ms']:>7}{r['realtime_factor']:>5}  {r['lang']}")
    print()
    for r in rows:
        print(f"[{r['id']}] " + " | ".join(r["explain"]))
    # sanity: control must be the lowest
    ctrl = next(r for r in rows if r["kind"] == "normal")
    worst = max(rows, key=lambda r: r["urgency"])
    ok = all(ctrl["urgency"] <= r["urgency"] for r in rows) and worst["kind"] != "normal"
    print(f"\ncontrol lowest: {'PASS' if ok else 'FAIL'}  (normal-query={ctrl['urgency']}, max={worst['id']}={worst['urgency']})")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
