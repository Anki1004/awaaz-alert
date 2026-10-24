"""
Does the system survive telephone audio? Real helpline calls arrive as 8 kHz G.711 (mu-law / A-law); every other
test in this repo uses clean 16 kHz. This re-encodes each sample through G.711 mu-law at 8 kHz (what an SBC / SIP
gateway hands us) and compares against the wideband result.

  python eval_narrowband.py [--codec pcm_mulaw|pcm_alaw]     # API on 127.0.0.1:8765
"""
import json, subprocess, sys, tempfile
from pathlib import Path
from eval import post_file

ROOT = Path(__file__).resolve().parent.parent / "samples"


def narrow(src: Path, codec: str, out: Path):
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(src), "-ar", "8000", "-ac", "1", "-acodec", codec, str(out)], check=True)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    codec = sys.argv[sys.argv.index("--codec") + 1] if "--codec" in sys.argv else "pcm_mulaw"
    items = []
    for meta, expect_key in (("samples.json", "kind"), ("hard/hard.json", "expect"), ("heldout/heldout.json", "expect")):
        base = (ROOT / meta).parent
        for m in json.loads((ROOT / meta).read_text(encoding="utf-8")):
            exp = m.get(expect_key)
            alert = (exp in ("fraudster", "victim", "alert"))
            items.append((m["id"], base / m["file"], alert))
    rows = []
    with tempfile.TemporaryDirectory() as td:
        for sid, wav, alert in items:
            if not wav.exists():
                continue
            nb = Path(td) / (sid + ".wav"); narrow(wav, codec, nb)
            a = post_file(wav)["overall"]; b = post_file(nb)["overall"]
            rows.append((sid, alert, a["urgency"], a["level"], b["urgency"], b["level"]))
    print(f"{'sample':<24}{'label':<9}{'16k urg':>8} {'level':<9}{'8k '+codec[4:]:>12} {'level':<9}")
    for sid, alert, ua, la, ub, lb in rows:
        print(f"{sid:<24}{'alert' if alert else 'quiet':<9}{ua:>8} {la:<9}{ub:>12} {lb:<9}")
    def stats(idx):
        tp = sum(1 for r in rows if r[1] and r[idx] in ("medium", "high", "critical")); fn = sum(1 for r in rows if r[1]) - tp
        fp = sum(1 for r in rows if not r[1] and r[idx] in ("medium", "high", "critical")); tn = sum(1 for r in rows if not r[1]) - fp
        return tp, fn, fp, tn
    for name, idx in (("16 kHz", 3), ("8 kHz " + codec[4:], 5)):
        tp, fn, fp, tn = stats(idx); print(f"{name:<14} scams caught {tp}/{tp+fn}   false alerts {fp}/{fp+tn}")
    drift = [abs(r[4] - r[2]) for r in rows]
    print(f"urgency drift 16k -> 8k: mean {sum(drift)/len(drift):.1f}, max {max(drift)}")

main()
