"""
Synthesise demo calls with edge-tts (Hindi/Indian-English neural voices) so the demo never depends on
real victim audio. These are scripted, labelled scenarios; emotion in TTS is flat, so they mainly
exercise the transcript -> fraud-script path and the live pipeline. Real recordings (consented) go
in samples/ with the same metadata format.

  python make_samples.py
"""
import asyncio
import json
import subprocess
from pathlib import Path

import edge_tts

OUT = Path(__file__).resolve().parent.parent / "samples"
OUT.mkdir(exist_ok=True)

# (id, voice, title, kind, note, lines[(speaker, text)])
SCRIPTS = [
    ("digital-arrest", "hi-IN-MadhurNeural", "Digital arrest — scammer side", "fraudster",
     "Classic 'CBI officer' script: impersonation + threat + secrecy + payment.",
     [
         "Namaste, main CBI Mumbai cyber cell se Inspector Rajesh Verma bol raha hoon.",
         "Aapke naam se ek parcel pakda gaya hai jisme drugs aur fake passport hain.",
         "Aapke Aadhaar card par money laundering ka case darj hai, arrest warrant nikal chuka hai.",
         "Aap abhi digital arrest mein hain. Video call par rahiye, phone mat kaatna, kisi ko mat batana.",
         "Verification ke liye aapko apna account ka paisa RBI ke safe account mein transfer karna hoga, abhi, turant.",
         "Agar do ghante mein transfer nahi hua toh police aapke ghar aa jayegi.",
     ]),
    ("victim-distress", "hi-IN-SwaraNeural", "Victim calling 1930 after loss", "victim",
     "Victim-side distress words + loss report; should score high on victim_loss and urgency.",
     [
         "Hello, 1930? Please meri madad kijiye, mere saath fraud ho gaya hai.",
         "Kisi ne CBI officer bankar video call kiya, bola digital arrest hai, aur maine darr ke maare paise transfer kar diye.",
         "Mere account se do lakh pachaas hazaar rupaye nikal gaye hain, abhi dus minute pehle.",
         "Main bahut dar gayi hoon, kya karoon? Paisa wapas aa sakta hai kya? Please bacha lijiye.",
     ]),
    ("kyc-otp", "hi-IN-MadhurNeural", "Bank KYC / OTP scam", "fraudster",
     "Bank impersonation + account block threat + OTP request.",
     [
         "Sir, main SBI head office se bol raha hoon. Aapka KYC pending hai.",
         "Aaj raat baarah baje aapka account block ho jayega aur ATM card bhi band ho jayega.",
         "KYC update ke liye abhi aapke phone par ek OTP aaya hoga, woh OTP mujhe bata dijiye.",
         "Ya phir AnyDesk app download karke screen share kijiye, hum khud kar denge.",
     ]),
    ("normal-query", "hi-IN-SwaraNeural", "Routine query — low priority", "normal",
     "Control sample: calm informational call, should stay low.",
     [
         "Namaste, main yeh jaanna chahti thi ki online complaint ka status kaise check karte hain.",
         "Maine pichle hafte portal par complaint darj ki thi, uska acknowledgement number mere paas hai.",
         "Koi jaldi nahi hai, bas process samajhna tha. Dhanyavaad.",
     ]),
    ("task-scam", "en-IN-PrabhatNeural", "Part-time task / investment scam", "fraudster",
     "English-Hinglish mix: payment + urgency, Telegram task scam.",
     [
         "Hi, I am calling from the HR team. You have been selected for a part time job, earn five thousand rupees daily.",
         "Just complete simple tasks on Telegram, like YouTube video likes, and double your investment.",
         "First you pay a small security deposit of two thousand through UPI, it is fully refundable.",
         "Offer is only valid today, please transfer immediately, last chance.",
     ]),
]


async def synth(voice: str, text: str, path: Path):
    await edge_tts.Communicate(text, voice, rate="+5%").save(str(path))


async def main():
    meta = []
    for sid, voice, title, kind, note, lines in SCRIPTS:
        parts = []
        for i, line in enumerate(lines):
            p = OUT / f"_{sid}_{i}.mp3"
            await synth(voice, line, p)
            parts.append(p)
        # concatenate with 0.6 s gaps -> 16 kHz mono wav
        lst = OUT / f"_{sid}.txt"
        lst.write_text("".join(f"file '{p.name}'\nfile 'silence.wav'\n" for p in parts), encoding="utf-8")
        if not (OUT / "silence.wav").exists():
            subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "anullsrc=r=16000:cl=mono", "-t", "0.6", str(OUT / "silence.wav")], check=True)
        wav = OUT / f"{sid}.wav"
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-ac", "1", "-ar", "16000", str(wav)], check=True, cwd=OUT)
        for p in parts: p.unlink()
        lst.unlink()
        dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(wav)], capture_output=True, text=True).stdout.strip() or 0)
        meta.append({"id": sid, "file": wav.name, "title": title, "kind": kind, "note": note, "duration": round(dur, 1), "synthetic": True, "script": lines})
        print(f"{sid}: {dur:.1f}s")
    (OUT / "silence.wav").unlink(missing_ok=True)
    (OUT / "samples.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print("wrote samples.json")


if __name__ == "__main__":
    asyncio.run(main())
