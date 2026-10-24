"""
Hard-case regression set (synthetic, labelled BEFORE it was ever scored — the labels below are the ones written
first and are not tuned to the output). It targets the failure modes a triage score must survive:
  * calm victims reporting a real loss (no emotion, no scam script)
  * a frightened caller who uses none of the scam vocabulary
  * legitimate calls that contain scary words (OTP, police, parcel, customs, KYC, block)
  * scam scripts outside the five demo samples (customs fee, lottery, trading group)

TTS voices are flat, so this tests the TRANSCRIPT + LEXICON path honestly and says nothing about real-voice
emotion. It is a regression test, not evidence of real-world accuracy.

  python make_hard_cases.py        -> samples/hard/*.wav + samples/hard/hard.json
"""
import asyncio, json, subprocess
from pathlib import Path
import edge_tts

OUT = Path(__file__).resolve().parent.parent / "samples" / "hard"
OUT.mkdir(parents=True, exist_ok=True)
SW, MA, PR, NE = "hi-IN-SwaraNeural", "hi-IN-MadhurNeural", "en-IN-PrabhatNeural", "en-IN-NeerjaNeural"

# (id, voice, expect, why, text, tts kwargs)
CASES = [
    ("calm-victim-loss", SW, "alert", "Calm caller, real loss: must outrank routine despite flat affect.",
     "Namaste, kal shaam mere account se do lakh rupaye kisi ne transfer kar liye. Mujhe complaint darj karni hai, kripya reference number bata dijiye.", {}),
    ("calm-victim-otp", MA, "alert", "Calm caller who already gave an OTP and lost money.",
     "Mujhe ek call aaya tha jisme unhone OTP maanga aur maine bata diya. Ab mere account se paisa nikal gaya hai.", {}),
    ("scared-no-keywords", SW, "alert", "Frightened, uses none of the scam vocabulary (voice path only).",
     "Please, mujhe bahut darr lag raha hai, samajh nahi aa raha main kya karun, koi mere saath hai, please jaldi aaiye!", {"rate": "+25%", "pitch": "+20Hz", "volume": "+20%"}),
    ("customs-fee-scam", NE, "alert", "English impersonation + payment + threat, not in the demo set.",
     "This is the customs department. A package in your name contains illegal items. You must pay a clearance fee today or you will be arrested.", {}),
    ("lottery-scam", MA, "alert", "Prize + processing-fee script.",
     "Badhai ho, aapne KBC lottery mein pachaas lakh rupaye jeete hain. Prize lene ke liye pehle processing fee jama kijiye.", {}),
    ("trading-group-scam", PR, "alert", "Investment-group script.",
     "Sir, humare trading group mein join kijiye, har din paisa double hota hai, bas pehle thoda amount bhejna padega.", {}),
    ("legit-upi-otp", SW, "no-alert", "Legitimate: own UPI OTP, failed payment.",
     "Namaste, mujhe bank se apne hi UPI payment ka OTP aaya tha, lekin payment fail ho gaya. Kya main dobara try kar sakta hoon?", {}),
    ("legit-police-address", MA, "no-alert", "Legitimate: police station address for passport verification.",
     "Mujhe passport verification ke liye police station ka address aur timing chahiye.", {}),
    ("legit-courier", SW, "no-alert", "Legitimate: courier tracking says customs.",
     "Mera courier Delhi se aana tha, tracking par dikha raha hai ki parcel customs mein ruka hua hai. Kitna time lagega, kya aap bata sakte hain?", {}),
    ("legit-kyc-block", MA, "no-alert", "Legitimate: KYC done, only asking about block.",
     "Mera bank KYC update ho chuka hai, branch mein documents bhi jama kar diye the. Bas confirm karna tha ki account block toh nahi hoga.", {}),
    ("legit-helpline-hours", NE, "no-alert", "Easy negative.",
     "Hello, I wanted to know the working hours of the cyber crime helpline.", {}),
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
    (OUT / "hard.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {len(meta)} cases")

asyncio.run(main())
