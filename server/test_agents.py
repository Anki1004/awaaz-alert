"""Fast transcript-level contract tests for AwaazAlert's agent layer."""
import unittest

from agents import run_agents
from fraud_lexicon import scan


def review(text: str, base: int = 18):
    return run_agents(text=text, fraud=scan(text), distress=0.02, arousal=0.1,
                      rate_term=0.05, prosody={"speech": True}, base_urgency=base)


class MultiAgentTriageTests(unittest.TestCase):
    def test_utility_disconnection_plus_immediate_upi_demand_is_medium(self):
        text = ("Your electricity connection will be disconnected tonight because the bill is unpaid. "
                "Pay two thousand rupees immediately on this UPI number to avoid it.")
        result = review(text)
        self.assertGreaterEqual(result["final_urgency"], 40)
        self.assertIn("Contextual coercion agent", [a["name"] for a in result["agents"]])

    def test_trai_sim_threat_and_coercion_is_high_priority(self):
        text = ("Main TRAI se bol raha hoon. Aapke number se illegal calls ho rahi hain, "
                "aapka SIM aaj raat block ho jayega. Verification ke liye abhi mere saath line par rahiye.")
        result = review(text)
        self.assertGreaterEqual(result["final_urgency"], 60)
        self.assertTrue(any("SIM/number threat" in e for a in result["agents"] for e in a["evidence"]))

    def test_prize_with_upfront_fee_gets_medium_review(self):
        text = "You have won a WhatsApp lucky draw. To release the prize please pay the processing fee today."
        self.assertGreaterEqual(review(text)["final_urgency"], 40)

    def test_first_person_loss_is_not_downgraded_for_flat_voice(self):
        text = "Namaste, mere UPI se teen baar paise kat gaye, main ne kuch kiya nahi, kripya check kar dijiye."
        result = review(text)
        self.assertGreaterEqual(result["final_urgency"], 35)
        self.assertTrue(any(a["name"] == "Victim-protection agent" and a["floor"] == 35 for a in result["agents"]))

    def test_legitimate_sim_block_request_has_no_contextual_floor(self):
        text = "Mera phone kho gaya hai, mujhe apna SIM block karwana hai, uske liye kaun sa number dial karna hoga?"
        result = review(text, base=12)
        self.assertEqual(result["urgency_floor"], 0)
        self.assertEqual(result["final_urgency"], 12)

    def test_legitimate_bill_question_has_no_contextual_floor(self):
        text = "Mere ghar ka bijli ka bill is mahine zyada aaya hai, main online payment kaise kar sakta hoon?"
        result = review(text, base=10)
        self.assertEqual(result["urgency_floor"], 0)
        self.assertEqual(result["final_urgency"], 10)

    def test_legitimate_bank_otp_question_has_no_contextual_floor(self):
        text = "Could you tell me my bank branch timings and whether OTP can be changed to a new mobile number?"
        result = review(text, base=8)
        self.assertEqual(result["urgency_floor"], 0)
        self.assertEqual(result["final_urgency"], 8)

    def test_agents_never_lower_the_base_score_and_do_not_claim_probabilities(self):
        result = review("Hello, I need the cyber helpline working hours.", base=77)
        self.assertEqual(result["final_urgency"], 77)
        self.assertTrue(all("score" in a and "evidence" in a for a in result["agents"]))
        self.assertTrue(all("probability" not in str(a).lower() for a in result["agents"]))


if __name__ == "__main__":
    unittest.main()
