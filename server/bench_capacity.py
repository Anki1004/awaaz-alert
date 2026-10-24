"""
How many simultaneous calls can ONE machine keep up with in real time? Streams N copies of a sample through
/ws/ingest as 8 kHz G.711 mu-law, paced at 20 ms per frame exactly like a media gateway, and measures how far behind
real time each window result arrives ("lag"). A stream is keeping up when lag stays small and does not grow.

  AWAAZ_MAX_SESSIONS=16 python main.py            # in another terminal: lift admission control for the test
  python bench_capacity.py 1 2 3 4 6              # concurrency levels to try
  python bench_capacity.py --key <API_KEY> --url ws://host:8765 2 4

Reads the sample from ../samples (digital-arrest.wav by default); needs ffmpeg and `pip install websockets`.
"""
import asyncio
import json
import statistics
import subprocess
import sys
import time
from pathlib import Path

import websockets

ROOT = Path(__file__).resolve().parent.parent
FRAME_MS = 20
WINDOW_S = 3.0


def load_mulaw(path: Path) -> bytes:
    return subprocess.run(["ffmpeg", "-loglevel", "error", "-i", str(path), "-ar", "8000", "-ac", "1", "-f", "mulaw", "pipe:1"],
                          capture_output=True, check=True).stdout


async def one_stream(url: str, key: str | None, audio: bytes, idx: int) -> dict:
    sub = [f"bearer.{key}"] if key else None
    lags, urg = [], []
    t0 = time.monotonic()
    async with websockets.connect(f"{url}/ws/ingest", subprotocols=sub, max_size=None, ping_interval=None) as ws:
        await ws.send(json.dumps({"line_id": f"bench-{idx}", "codec": "pcmu", "rate": 8000}))
        hello = json.loads(await ws.recv())
        if hello.get("type") != "hello":
            return {"error": hello}
        t0 = time.monotonic()
        step = 8 * FRAME_MS                     # 8 bytes per ms at 8 kHz mu-law

        async def sender():
            for i in range(0, len(audio), step):
                await ws.send(audio[i:i + step])
                await asyncio.sleep(max(0, (i // step + 1) * FRAME_MS / 1000 - (time.monotonic() - t0)))
            await asyncio.sleep(WINDOW_S + 8)   # let the last windows come back
            await ws.close()

        async def receiver():
            k = 0
            try:
                async for raw in ws:
                    m = json.loads(raw)
                    if m.get("type") == "window":
                        k += 1
                        lags.append(time.monotonic() - t0 - k * WINDOW_S)
                        urg.append(m["data"]["urgency"])
            except websockets.ConnectionClosed:
                pass

        await asyncio.gather(sender(), receiver())
    return {"lags": lags, "urg": urg}


async def run_level(n: int, url: str, key: str | None, audio: bytes):
    res = await asyncio.gather(*[one_stream(url, key, audio, i) for i in range(n)], return_exceptions=True)
    ok = [r for r in res if isinstance(r, dict) and "lags" in r]
    bad = [r for r in res if not (isinstance(r, dict) and "lags" in r)]
    allags = [x for r in ok for x in r["lags"]]
    if not allags:
        print(f"N={n}: no windows received; failures: {bad[:2]}")
        return None
    tail = [statistics.mean(r["lags"][-3:]) for r in ok if len(r["lags"]) >= 3]
    row = dict(n=n, windows=len(allags), p50=statistics.median(allags), p95=sorted(allags)[int(0.95 * (len(allags) - 1))],
               worst=max(allags), tail=max(tail) if tail else float("nan"), failed=len(bad))
    verdict = "keeps up" if row["p95"] < 2.5 and row["tail"] < 3.0 else "FALLS BEHIND"
    print(f"N={n:<2} windows={row['windows']:<4} lag p50={row['p50']:5.2f}s p95={row['p95']:5.2f}s worst={row['worst']:5.2f}s "
          f"end-of-call lag={row['tail']:5.2f}s failed={row['failed']}  -> {verdict}")
    return row


async def main():
    args = sys.argv[1:]
    key = url = None
    url = "ws://127.0.0.1:8765"
    if "--key" in args:
        i = args.index("--key"); key = args[i + 1]; del args[i:i + 2]
    if "--url" in args:
        i = args.index("--url"); url = args[i + 1]; del args[i:i + 2]
    levels = [int(a) for a in args] or [1, 2, 4]
    audio = load_mulaw(ROOT / "samples" / "digital-arrest.wav")
    print(f"{len(audio) / 8000:.0f} s of 8 kHz mu-law per stream, {FRAME_MS} ms frames, window {WINDOW_S:.0f} s")
    print("warm-up (first call pays CUDA/model warm-up and is not a fair measurement)...")
    await one_stream(url, key, audio[:8000 * 12], 99)
    await asyncio.sleep(2)
    for n in levels:
        await run_level(n, url, key, audio)
        await asyncio.sleep(3)


asyncio.run(main())
