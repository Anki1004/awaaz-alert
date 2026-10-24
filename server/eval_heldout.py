"""
Score the held-out set against (a) AwaazAlert (alert = level medium or above) and (b) a naive keyword baseline
(alert = the Hinglish scam lexicon matches anything in the transcript). Prints confusion counts for both.
Synthetic voices: a regression test of the transcript/lexicon path, NOT a real-world accuracy figure.

  python eval_hard.py      # needs the API on 127.0.0.1:8765 and `python make_heldout.py` run once
"""
import json, sys
from pathlib import Path
import fraud_lexicon as L
from eval import post_file

HARD = Path(__file__).resolve().parent.parent / "samples" / "heldout"


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    meta = json.loads((HARD / "heldout.json").read_text(encoding="utf-8"))
    rows = []
    for c in meta:
        res = post_file(HARD / c["file"])
        o = res["overall"]
        text = " ".join(w["transcript"] for w in res["windows"] if w.get("transcript"))
        base = bool(L.scan(text)["matches"])
        ours = o["level"] in ("medium", "high", "critical")
        rows.append({**c, "urgency": o["urgency"], "level": o["level"], "sig": o["signature"], "conf": o.get("asr_confidence"), "evidence": "-", "ours": ours, "base": base, "heard": text})
    print(f"{'case':<22}{'expect':<10}{'urg':>4} {'level':<9}{'AwaazAlert':<12}{'keyword-only':<13}{'asr':>5} {'evid':<8}heard")
    for r in rows:
        want = r["expect"] == "alert"
        mark = lambda got: ("ok " if got == want else "MISS" if want else "FALSE") + (" alert" if got else " quiet")
        print(f"{r['id']:<22}{r['expect']:<10}{r['urgency']:>4} {r['level']:<9}{mark(r['ours']):<12}{mark(r['base']):<13}{(r['conf'] if r['conf'] is not None else 0):>5} {str(r['evidence']):<8}{r['heard'][:44]}")
    def conf(key):
        tp = sum(1 for r in rows if r["expect"] == "alert" and r[key]); fn = sum(1 for r in rows if r["expect"] == "alert" and not r[key])
        fp = sum(1 for r in rows if r["expect"] != "alert" and r[key]); tn = sum(1 for r in rows if r["expect"] != "alert" and not r[key])
        return tp, fn, fp, tn
    for name, key in (("AwaazAlert", "ours"), ("keyword-only", "base")):
        tp, fn, fp, tn = conf(key)
        print(f"{name:<13} recall {tp}/{tp+fn}  false alerts {fp}/{fp+tn}  (TP {tp} FN {fn} FP {fp} TN {tn})")
    (HARD / "results.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")

main()
