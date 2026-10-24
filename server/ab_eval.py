# In-process A/B: ASR vocabulary prompt on vs off, all samples. Prints urgency / fraud / signature per sample.
import json, os, sys, importlib
sys.stdout.reconfigure(encoding="utf-8")
import pipeline as P
P.load_models()
meta = json.load(open('../samples/samples.json', encoding='utf-8'))
for use in (True, False):
    P.USE_PROMPT = use
    print(f"\n=== prompt {'ON' if use else 'OFF'}")
    for s in meta:
        r = P.analyze_file(open(f"../samples/{s['file']}", 'rb').read())
        o = r['overall']
        print(f"{s['id']:<17}{o['urgency']:>4} {o['level']:<8}{str(o['signature'] or '-'):<24} fraud={o['fraud']['score']:.2f}  lat={o['avg_latency_ms']}ms  | {o['transcript'][:110]}")
