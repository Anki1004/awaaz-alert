"""
HELD-OUT set: written and labelled after the lexicon fixes made on the hard set, and scored exactly once. Never edit
the lexicon against these cases; add new ones instead. It targets the failure modes a triage score must survive:
  * calm victims reporting a real loss (no emotion, no scam script)
  * a frightened caller who uses none of the scam vocabulary
  * legitimate calls that contain scary words (OTP, police, parcel, customs, KYC, block)
  * scam scripts outside the five demo samples (customs fee, lottery, trading group)

TTS voices are flat, so this tests the TRANSCRIPT + LEXICON path honestly and says nothing about real-voice
emotion. It is a regression test, not evidence of real-world accuracy.

  python make_hard_cases.py        -> samples/heldout/*.wav + samples/heldout/heldout.json
"""
import asyncio, json, subprocess
from pathlib import Path
import edge_tts

OUT = Path(__file__).resolve().parent.parent / "samples" / "heldout"
OUT.mkdir(parents=True, exist_ok=True)
SW, MA, PR, NE = "hi-IN-SwaraNeural", "hi-IN-MadhurNeural", "en-IN-PrabhatNeural", "en-IN-NeerjaNeural"

# (id, voice, expect, why, text, tts kwargs)
CASES = [
    ("h-calm-loss-upi", SW, "alert", "Calm loss report, different wording.",
     "Namaste, mere UPI se teen baar paise kat gaye, main ne kuch kiya nahi, kripya check kar dijiye aur batayiye kya karna chahiye.", {}),
    ("h-sim-trai-scam", MA, "alert", "TRAI / SIM-block impersonation.",
     "Main TRAI se bol raha hoon. Aapke number se illegal calls ho rahi hain, aapka SIM aaj raat block ho jayega. Verification ke liye abhi mere saath line par rahiye.", {}),
    ("h-electricity-scam", PR, "alert", "Electricity-disconnection scam.",
     "Sir, your electricity connection will be disconnected tonight because the bill is unpaid. Pay two thousand rupees immediately on this UPI number to avoid it.", {}),
    ("h-family-emergency", SW, "alert", "Family-emergency scam, victim-side after paying.",
     "Mere bete ke naam se kisi ne call kiya, bola accident ho gaya hai, paise bhejo. Maine bhej diye, ab uska phone band hai, mujhe darr lag raha hai.", {"rate": "+15%"}),
    ("h-kbc-whatsapp", NE, "alert", "WhatsApp lottery with fee.",
     "Congratulations, you have won twenty five lakh in the WhatsApp lucky draw. To release the prize please pay the processing fee today.", {}),
    ("h-legit-sim-lost", SW, "no-alert", "Legitimate: lost SIM, wants to block it.",
     "Mera phone kho gaya hai, mujhe apna SIM block karwana hai, uske liye kaun sa number dial karna hoga?", {}),
    ("h-legit-bill-query", MA, "no-alert", "Legitimate: own electricity bill question.",
     "Mere ghar ka bijli ka bill is mahine zyada aaya hai, main online payment kaise kar sakta hoon aur receipt kahan milegi?", {}),
    ("h-legit-police-callback", SW, "no-alert", "Legitimate: wants to reach the investigating officer on his own case.",
     "Meri complaint par police ne jaanch shuru ki thi, main investigating officer se baat karna chahti hoon, unka number kahan se milega?", {}),
    ("h-legit-bank-hours", NE, "no-alert", "Legitimate: bank branch timings.",
     "Could you tell me the timings of my bank branch and whether the OTP for net banking can be changed to a new mobile number?", {}),
]


async def main():
    meta = []
    for cid, voice, expect, why, text, kw in CASES:
        mp3 = OUT / f"_{cid}.mp3"
        await edge_tts.Communicate(text, voice, **({"rate": "+5%"} | kw)).save(str(mp3))
        wav = OUT / f"{cid}.wav"
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(mp3), "-ac", "1", "-ar", "16000", str(wav)], check=True)
        mp3.unlink()
        meta.append({"id": cid, "file": wav.name, "expect": expect, "why": why, "text": text, "synthetic": True})
    (OUT / "heldout.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {len(meta)} cases")

asyncio.run(main())
