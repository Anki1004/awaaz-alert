"""AwaazAlert's deterministic multi-agent triage layer.

Each agent owns one narrow evidence family. These are local rule/model wrappers, not LLMs and
not calibrated probabilities. The adjudicator can raise the existing urgency score when a
specific, explainable context pattern deserves a human review. It never lowers the base score.
"""
from __future__ import annotations

import re


def _rx(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern, re.IGNORECASE)


# Contextual patterns require combinations. An isolated mention of a bank, SIM, bill, police,
# OTP or prize must not be treated as evidence that a call is fraudulent.
_UTILITY = _rx(r"\b(electricity|electric|power connection|bijli|bijlee)\b|बिजली|बिजली कनेक्शन")
_DISCONNECT = _rx(r"\b(disconnect(?:ed|ion)?|cut off|suspend(?:ed)?|power will be cut|band ho jayega|sim block)\b|बंद हो जाएगा|काट दिया जाएगा|डिस्कनेक्ट|ब्लॉक हो जाएगा")
_PAYMENT_DEMAND = _rx(r"\b(pay|payment|transfer|send|upi|paytm|phonepe|processing fee|clearance fee|security deposit|deposit|rupees|amount bhejo|paisa bhejo|paise bhejo|jama kijiye|fee jama)\b|₹|रुपये भेज|पैसे भेज|रकम जमा|फीस जमा")
_URGENT = _rx(r"\b(immediately|right now|tonight|today|urgent|within|abhi|turant|jaldi|aaj hi|aaj raat)\b|तुरंत|अभी|आज ही|आज रात|जल्दी")
_UPI_CHANNEL = _rx(r"\b(upi|paytm|phonepe|gpay|google pay|personal account|wallet)\b|यूपीआई|फोनपे|पेटीएम")
_AUTHORITY = _rx(r"\b(trai|cbi|enforcement directorate|ed\b|police|customs|narcotics|cyber cell|court|income tax|telecom department|bank officer|rbi)\b|ट्राई|सीबीआई|पुलिस|कस्टम|नारकोटिक्स|साइबर सेल")
_SIM_OR_NUMBER = _rx(r"\b(sim|mobile number|phone number|telephone number|connection)\b|सिम|मोबाइल नंबर|फोन नंबर")
_BLOCK_THREAT = _rx(r"\b(block(?:ed)?|suspend(?:ed)?|disconnect(?:ed|ion)?|deactivate|arrest|warrant|jail|case filed|illegal calls)\b|ब्लॉक|सस्पेंड|बंद हो जाएगा|गिरफ्तार|वारंट|अवैध कॉल")
_COERCION = _rx(r"\b(stay on the line|don't hang up|do not hang up|line par rahiye|line par raho|verification ke liye|verify now|kisi ko mat batana|secret|confidential|otherwise|or you will)\b|फोन मत काट|किसी को मत बताना|लाइन पर रह|वेरिफिकेशन के लिए")
_PRIZE = _rx(r"\b(lottery|won|winner|prize|lucky draw|kbc|jackpot|release the prize)\b|लॉटरी|इनाम|केबीसी|लकी ड्रॉ|जीत गए|जीता है")
_UPFRONT_FEE = _rx(r"\b(processing fee|release fee|clearance fee|pay .*fee|fee .*pay|deposit|send .*rupees|pay .*rupees|payment to release|before you receive)\b|प्रोसेसिंग फीस|फीस जमा|पहले .*जमा|रिलीज करने के लिए .*फीस")
_CREDENTIAL = _rx(r"\b(otp|one time password|upi pin|pin number|password|anydesk|teamviewer|quick support|screen share|remote access)\b|ओटीपी|पासवर्ड|पिन नंबर|स्क्रीन शेयर|एनीडेस्क")
_CREDENTIAL_ASK = _rx(r"\b(share|tell|give|send|provide|enter|install|download|batao|bata dijiye|bata dena|de do|bhejo|bhej do|maang raha|maanga|screen share)\b|बता दीजिए|बता दो|भेज दो|शेयर करो|इंस्टॉल|डाउनलोड|मांग रहा|मांगा")
_LOSS_REPORT = _rx(r"\b(paise? (?:kat|nikal|chale|ud) gaye|account se .*?(?:paise|paisa|money|amount) .*?(?:nikal|transfer|debit)|fraud ho gaya|scam ho gaya|otp .*?(?:bata diya|share kar diya)|maine .*?(?:transfer kar diya|bhej diye|bhej diya))\b|पैसे कट गए|पैसे निकल गए|अकाउंट से .*पैसे .*निकल|फ्रॉड हो गया|स्कैम हो गया|ओटीपी .*बता दिया")
_FIRST_PERSON_PAYMENT_AFTER_CALL = _rx(r"\b(kisi ne call kiya|someone called|mere (?:bete|beta|beti|son|daughter)|accident ho gaya)\b.{0,140}\b(paise bhejo|send money|maine bhej diye|bhej diye|sent the money|paid them)\b")


def _has(pattern: re.Pattern[str], text: str) -> bool:
    return bool(pattern.search(text or ""))


def _clamp(value: float) -> float:
    return round(min(1.0, max(0.0, float(value))), 3)


def _agent(name: str, score: float, evidence: list[str], floor: int = 0, status: str | None = None) -> dict:
    score = _clamp(score)
    return {
        "name": name,
        "status": status or ("signal" if evidence else "no_signal"),
        "score": score,  # signal strength, not a probability of fraud
        "floor": int(floor),
        "evidence": evidence[:5],
    }


def run_agents(
    *,
    text: str,
    fraud: dict,
    distress: float,
    arousal: float,
    rate_term: float,
    prosody: dict,
    base_urgency: int,
) -> dict:
    """Run independent evidence agents and a deterministic adjudicator.

    The base score is preserved. A documented triage floor can increase human-review priority,
    but this layer never lowers urgency and never labels a caller as guilty or dishonest.
    """
    transcript = (text or "").strip()
    cats = fraud.get("categories") or {}
    signature = fraud.get("signature")
    findings: list[dict] = []

    # 1. Acoustic agent: only measured model/prosody/rate values.
    acoustic_score = 0.65 * _clamp(distress) + 0.25 * _clamp(arousal) + 0.10 * _clamp(rate_term)
    acoustic_evidence = []
    if distress >= 0.35:
        acoustic_evidence.append(f"emotion-derived distress signal {distress:.2f}")
    if prosody.get("speech") and arousal >= 0.65:
        acoustic_evidence.append(f"prosody differs from caller baseline (arousal {arousal:.2f})")
    if rate_term >= 0.4:
        acoustic_evidence.append(f"speech-rate signal {rate_term:.2f}")
    findings.append(_agent("Acoustic distress agent", acoustic_score, acoustic_evidence,
                           status="signal" if acoustic_evidence else "no_signal"))

    # 2. Script agent: uses the existing Hinglish fraud lexicon and named signatures.
    hit_categories = sorted(k for k, v in cats.items() if float(v or 0) >= 0.4)
    script_evidence = []
    if signature:
        script_evidence.append(f"named script pattern: {signature}")
    if hit_categories:
        script_evidence.append("matched categories: " + ", ".join(hit_categories))
    findings.append(_agent("Fraud-script agent", float(fraud.get("score") or 0), script_evidence,
                           floor=40 if signature else 0))

    # 3. Context/pressure agent: escalates combinations, not isolated scary words.
    context_evidence: list[str] = []
    context_scores: list[float] = []
    context_floors: list[int] = []
    has_payment = _has(_PAYMENT_DEMAND, transcript)
    has_urgent = _has(_URGENT, transcript)
    has_authority = _has(_AUTHORITY, transcript)
    has_threat = _has(_BLOCK_THREAT, transcript)

    if (_has(_UTILITY, transcript) and _has(_DISCONNECT, transcript) and has_payment
            and (has_urgent or _has(_UPI_CHANNEL, transcript))):
        context_evidence.append("utility-disconnection threat paired with an urgent or UPI payment demand")
        context_scores.append(0.78)
        context_floors.append(40)

    if (has_authority and _has(_SIM_OR_NUMBER, transcript) and has_threat
            and _has(_COERCION, transcript)):
        context_evidence.append("authority claim + SIM/number threat + coercive verification or stay-on-line instruction")
        context_scores.append(0.92)
        context_floors.append(60)

    if (has_authority and has_threat and has_payment and (has_urgent or _has(_COERCION, transcript))):
        context_evidence.append("authority/legal threat paired with a payment demand")
        context_scores.append(0.92)
        context_floors.append(60)

    if _has(_PRIZE, transcript) and has_payment and _has(_UPFRONT_FEE, transcript):
        context_evidence.append("prize or lottery claim paired with an upfront fee")
        context_scores.append(0.76)
        context_floors.append(40)

    if _has(_CREDENTIAL, transcript) and _has(_CREDENTIAL_ASK, transcript):
        if has_authority or has_threat or has_urgent or _has(_COERCION, transcript):
            context_evidence.append("credential or remote-access request paired with pressure, urgency, or authority claims")
            context_scores.append(0.95)
            context_floors.append(60)

    findings.append(_agent("Contextual coercion agent", max(context_scores, default=0.0), context_evidence,
                           floor=max(context_floors, default=0)))

    # 4. Victim-protection agent: a calm loss report should not be ranked as routine.
    loss_report = (
        float(cats.get("victim_loss") or 0) >= 0.4
        or _has(_LOSS_REPORT, transcript)
        or _has(_FIRST_PERSON_PAYMENT_AFTER_CALL, transcript)
    )
    loss_evidence = ["possible first-person loss report; keep the call in human-review queue"] if loss_report else []
    findings.append(_agent("Victim-protection agent", 0.7 if loss_report else 0.0, loss_evidence,
                           floor=35 if loss_report else 0))

    # 5. Adjudicator: conservative, monotonic fusion.
    floor = max((int(item["floor"]) for item in findings), default=0)
    final_urgency = max(int(base_urgency), floor)
    adjudication_evidence = [f"base measured-feature urgency: {int(base_urgency)}"]
    if floor > int(base_urgency):
        sources = [item["name"] for item in findings if int(item["floor"]) == floor and floor > 0]
        adjudication_evidence.append(f"human-review floor {floor} applied by: {', '.join(sources)}")
    findings.append(_agent("Risk adjudicator", final_urgency / 100.0, adjudication_evidence,
                           floor=floor, status="escalated" if floor > int(base_urgency) else "base_score_kept"))

    escalation_reasons = [
        evidence
        for item in findings[:-1] if item["floor"] > 0
        for evidence in item["evidence"]
    ]
    return {
        "final_urgency": final_urgency,
        "urgency_floor": floor,
        "agents": findings,
        "escalation_reasons": list(dict.fromkeys(escalation_reasons))[:4] if floor > int(base_urgency) else [],
    }
