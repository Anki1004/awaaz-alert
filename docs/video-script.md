# AwaazAlert — 2-minute demo script

Record at 1440×900 in Chrome (dashboard at http://127.0.0.1:5173, server running). No login/signup to show.
Screen only + voice-over (Hinglish is fine for the voice; captions in English). Hard cap: 1:55.

| Time | On screen | Voice-over |
|---|---|---|
| 0:00–0:12 | Dashboard, Standby. Cursor rests on the banner "Indicative only". | "1930 cyber helpline par ek operator ke paas ek saath kai calls hoti hain — ek victim jo abhi 'digital arrest' mein hai, ek fraudster jo baited ho raha hai, ek routine query. AwaazAlert operator ke saath sunta hai aur har line ko ek honest, explainable urgency score deta hai. Yeh evidence nahi hai — sirf priority ka signal." |
| 0:12–0:40 | Click **▶ Digital arrest — scammer side** (normal speed). Let the pen trace draw; the "DIGITAL ARREST" stamp lands around 0:30. | "Yeh ek synthetic scam call hai. Dekhiye — paper strip par urgency ki pen chal rahi hai, aur neeche ink ticks: har tick ek fraud cue hai jo transcript mein mila. 'CBI', 'parcel', 'drugs', 'arrest warrant', 'phone mat kaatna' — teen categories ek saath lit hue, aur pattern naam ke saath stamp ho gaya: Digital arrest." |
| 0:40–0:58 | Point at **Why this line lit up**; then the **Script cues** meters; then toggle **Redact personal details** off → cues underline in the transcript. | "Har number measured hai — kaunse cues, kis category mein, pitch kitna upar gaya is caller ke apne baseline se. Transcript by default redacted hai — phone, Aadhaar, OTP digits kabhi screen par nahi aate; operator chahe toh reveal kar sakta hai." |
| 0:58–1:18 | Click **Score all samples**. Queue sorts: Digital arrest 65 · KYC/OTP 65 · Victim 59 · Task scam 50 · Routine 17. | "Ab paanch lines ek saath. Queue urgency se sort ho gayi: do scam scripts upar, victim beech mein, aur routine query sabse neeche sirf 17 par — control sample kabhi upar nahi aata. Yeh table hamari eval script bhi print karti hai." |
| 1:18–1:38 | Click **● Start live call**, speak 2 lines into the mic: calm "Hello, status check karna tha" then agitated "Sir please, mere account se paisa nikal gaya, abhi, madad kijiye!" Show the trace jump + Voice/Prosody meters. | "Live mic bhi — 3-second windows, 0.4 se 1.4 second latency on a laptop GPU. Pehli line calm, doosri mein 'paisa nikal gaya', 'madad' aur awaaz ka pitch is caller ke baseline se upar — urgency chadh gayi." |
| 1:38–1:55 | Back to standby. Show README "How it works" diagram for 3 s, then the dashboard. | "Teen independent signals — emotion2vec+, prosody, aur Hinglish fraud-script detection on a whisper transcript — ek fused score, hamesha explanation ke saath, kuch bhi store kiye bina. AwaazAlert." |

Do not say: accuracy percentages for emotion (we have none for Hindi); "detects lies"; "AI knows".
Do say: "indicative", "explainable", "nothing stored".
