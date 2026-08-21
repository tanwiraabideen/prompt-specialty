# Taxonomy v1: Bucket Definitions

Status: **DRAFT, not frozen.** Tanwir must review and confirm every tie-break rule in section 3 before labelling begins.

Serves three purposes:
1. Annotation guideline for the hand-labelled eval set
2. Taxonomy text pasted into the zero-shot classifier prompt
3. Spec for LLM-generated synthetic training data

**This is a ROUTING system, not a diagnostic one.** No definition below names a disease as an output. Symptom text goes in, a specialty bucket comes out. Where a condition name appears in an example, it is because the user typed it, not because the system infers it.

24 routable buckets. Five non-label groups (section 4) are excluded from the classifier's output space.

---

## 1. Reading the examples

Each bucket has:
- **Scope**: one line, what belongs here
- **In**: three symptom phrasings a layperson would actually type
- **Near-miss**: two that look like they belong but don't, with their true destination

Near-misses are the load-bearing part. They are the only thing preventing inconsistent labelling at the boundaries.

---

## 2. Bucket definitions

### general_medicine
**Scope:** Adult illness with no clear single organ system, first contact, general unwellness, routine checks. Absorbs GP, Family Medicine, Internal Medicine, Geriatrics.
- In: "tired for three months and I've lost weight without trying"
- In: "fever and body aches for four days now"
- In: "I feel generally unwell, I think I need blood tests"
- Near-miss: "burning when I urinate" → urology (single clear system)
- Near-miss: "chest pain spreading to my arm" → EMERGENCY prefilter

### pediatrics
**Scope:** Child complaints where age itself is the routing driver: general child illness, feeding, growth, development, newborns. NOT a catch-all for every child.
- In: "my 2 year old has a fever and won't eat anything"
- In: "newborn keeps vomiting after every feed"
- In: "my son is 4 and much smaller than other kids his age"
- Near-miss: "my 8 year old's teeth are crowded" → orthodontics
- Near-miss: "my child's ear hurts and he keeps pulling it" → ent, with `pediatric_capable` filter

### dentistry_general
**Scope:** Teeth: decay, pain, fractures, fillings, crowns, extractions, cleaning, implants, wisdom teeth, jaw and TMJ. Absorbs Endodontics, Prosthodontics, OMFS, Oral Medicine.
- In: "my back tooth hurts badly when I drink something cold"
- In: "I chipped my front tooth eating"
- In: "wisdom tooth area is swollen and I can't open my mouth properly"
- Near-miss: "my gums bleed every time I brush" → periodontics
- Near-miss: "I want my teeth straightened" → orthodontics

### orthodontics
**Scope:** Tooth alignment and bite: braces, aligners, spacing, crowding, jaw position.
- In: "my teeth are crowded and I want braces"
- In: "thinking about Invisalign, how much does it cost"
- In: "my top teeth stick out over my bottom teeth"
- Near-miss: "my tooth cracked" → dentistry_general
- Near-miss: "I want my teeth whiter" → dentistry_general (cosmetic dentistry)

### periodontics
**Scope:** Gums and tooth-supporting structures: bleeding, recession, gum disease, loose teeth.
- In: "my gums bleed every time I brush my teeth"
- In: "my gums are receding and my teeth look longer than before"
- In: "swollen gums and bad breath that won't go away"
- Near-miss: "my tooth is sensitive to cold" → dentistry_general
- Near-miss: "I'm missing a tooth and want an implant" → dentistry_general

### dermatology
**Scope:** Medical skin, hair, and nail conditions: rashes, acne, moles, hair loss, infections.
- In: "itchy red scaly patches on my elbows for weeks"
- In: "a mole on my back has changed colour and shape"
- In: "acne that isn't improving with anything from the pharmacy"
- Near-miss: "I want filler in my cheeks" → plastic_aesthetic
- Near-miss: "rash and swelling right after eating shellfish" → allergy_immunology

### plastic_aesthetic
**Scope:** Elective cosmetic alteration and reconstructive surgery: injectables, body contouring, rhinoplasty, hair transplant.
- In: "I want botox for my forehead lines"
- In: "considering a nose job, want a consultation"
- In: "hair transplant, my hairline is receding"
- Near-miss: "a mole has changed colour" → dermatology
- Near-miss: "my hair is falling out in patches" → dermatology (medical, not elective)

### obgyn
**Scope:** Pregnancy, childbirth, female reproductive system, menstrual and menopausal issues, fertility (female).
- In: "my periods are extremely painful every month"
- In: "I'm 8 weeks pregnant and need my first checkup"
- In: "bleeding between periods for the last two cycles"
- Near-miss: "we've been trying to conceive, the problem is with my husband" → urology
- Near-miss: "burning when I urinate, no other symptoms" → urology (see tie-break 3.6)

### cardiology
**Scope:** Heart and circulation, non-emergency: rhythm, blood pressure, exertional symptoms, known heart disease follow-up. Absorbs cardiac, cardiothoracic, vascular surgery, electrophysiology.
- In: "my heart races when I climb one flight of stairs"
- In: "pharmacy said my blood pressure is 160 over 100"
- In: "my ankles swell up by the end of every day"
- Near-miss: "crushing chest pain right now" → EMERGENCY prefilter
- Near-miss: "breathless with wheezing and a cough" → pulmonology

### gastroenterology
**Scope:** Digestive tract and liver: reflux, bowel habit, abdominal pain (non-acute), liver. Absorbs Hepatology.
- In: "burning in my upper stomach an hour after eating"
- In: "loose motions for three weeks now"
- In: "the whites of my eyes have gone yellow"
- Near-miss: "sudden severe stomach pain, I can't stand up straight" → EMERGENCY prefilter
- Near-miss: "I want to lose weight" → nutrition

### orthopedics
**Scope:** Musculoskeletal injury and structural problems: joints, bones, spine, fractures, sprains. Absorbs Podiatry, Sports Medicine.
- In: "my knee hurts every time I go down stairs"
- In: "shoulder pain, I can't lift my arm above my head"
- In: "twisted my ankle playing football, it's swollen"
- Near-miss: "I need rehab exercises after my knee surgery" → physiotherapy
- Near-miss: "multiple joints stiff for an hour every morning" → rheumatology

### physiotherapy
**Scope:** Rehabilitation, movement, posture, and recovery: post-operative, post-injury, chronic mechanical pain management.
- In: "I need physio after my knee replacement"
- In: "my neck is stiff from sitting at a desk all day"
- In: "the doctor told me to start rehab exercises for my back"
- Near-miss: "I fell and can't put weight on my ankle" → orthopedics
- Near-miss: "sudden back pain with numbness down my leg" → neurology

### ophthalmology
**Scope:** Eyes and vision: vision changes, eye pain, redness, discharge, floaters, screening.
- In: "my vision has been blurry for about a month"
- In: "red itchy eye with sticky discharge in the morning"
- In: "I keep seeing floaters and small flashes"
- Near-miss: "I've suddenly lost vision in one eye" → EMERGENCY prefilter
- Near-miss: "itchy scaly rash on my eyelid" → dermatology

### ent
**Scope:** Ear, nose, throat, hearing, balance, sinuses, voice. Absorbs Otolaryngology, Head and Neck Surgery, Audiology.
- In: "blocked nose and facial pressure for three weeks"
- In: "ear pain and everything sounds muffled"
- In: "my voice has been hoarse for over a month"
- Near-miss: "sneezing and itchy eyes every single morning" → allergy_immunology
- Near-miss: "sore throat with fever since yesterday" → general_medicine

### urology
**Scope:** Urinary tract in both sexes, male reproductive system, kidney stones. Absorbs Andrology, Urosurgery, Genito-Urinary Medicine.
- In: "burning and stinging when I urinate"
- In: "I'm getting up three times every night to urinate"
- In: "blood in my urine this morning"
- Near-miss: "swelling in my legs and frothy urine" → nephrology
- Near-miss: "no periods for three months and pelvic pain" → obgyn

### neurology
**Scope:** Brain and nervous system: headache, seizures, numbness, weakness, tremor, dizziness, memory. Absorbs Neurosurgery, Neuro and Spine.
- In: "headaches most days for the last two months"
- In: "numbness and tingling in both hands, worse at night"
- In: "my hand shakes when I try to hold a cup"
- Near-miss: "the worst headache of my life, came on suddenly" → EMERGENCY prefilter
- Near-miss: "dizzy for a few seconds when I turn over in bed" → ent

### pulmonology
**Scope:** Lungs and breathing: chronic cough, wheeze, breathlessness, sleep apnoea. Absorbs Respiratory Medicine, Chest Medicine, Thoracic Surgery, Sleep Medicine.
- In: "a cough that hasn't gone away in six weeks"
- In: "I wheeze at night and wake up short of breath"
- In: "my wife says I snore and stop breathing in my sleep"
- Near-miss: "I can't breathe properly right now" → EMERGENCY prefilter
- Near-miss: "breathless when walking, with swollen ankles" → cardiology

### endocrinology
**Scope:** Hormones and metabolism: diabetes, thyroid, adrenal, pituitary, metabolic disorders.
- In: "I'm diabetic and my sugar levels are out of control"
- In: "my thyroid blood test came back abnormal"
- In: "gaining weight, always cold, hair falling out"
- Near-miss: "I want a diet plan to lose weight" → nutrition
- Near-miss: "irregular periods with facial hair growth" → obgyn

### psychiatry
**Scope:** Mental health: mood, anxiety, sleep, attention, behaviour, addiction. Absorbs Counseling.
- In: "I feel anxious all the time and can't sleep"
- In: "low mood for months, no interest in anything"
- In: "my son can't focus at school and his teacher suggested an assessment"
- Near-miss: "tired all the time, no other symptoms" → general_medicine
- Near-miss: "can't sleep because of back pain" → orthopedics

> **SAFETY:** Text indicating self-harm, suicidal intent, or intent to harm others must NOT be routed to a psychiatry doctor listing. It goes to the crisis path, not the classifier. Same architectural position as the emergency prefilter.

### nephrology
**Scope:** Kidney function and disease: abnormal kidney results, kidney failure, dialysis, fluid retention of renal origin.
- In: "my kidney function test results came back abnormal"
- In: "swelling in my face and legs, and my urine is frothy"
- In: "I'm on dialysis and need a follow-up consultation"
- Near-miss: "burning when I urinate" → urology
- Near-miss: "severe pain in my side, comes in waves" → urology (stones)

### general_surgery
**Scope:** Conditions typically managed operatively by a general surgeon: hernia, gallbladder, appendix, lumps, piles, GI surgery. Absorbs Laparoscopic, Gastro-intestinal Surgery.
- In: "a lump in my groin that bulges when I cough"
- In: "pain under my right ribs after eating oily food"
- In: "bleeding when I pass stool, and something comes out"
- Near-miss: "sudden severe abdominal pain with fever" → EMERGENCY prefilter
- Near-miss: "heartburn and acid coming up my throat" → gastroenterology

### allergy_immunology
**Scope:** Allergy and immune response: hay fever, food and drug allergy, hives, recurrent infections. Absorbs Immunology.
- In: "sneezing and itchy eyes every morning, worse in dusty places"
- In: "rash and lip swelling after eating nuts"
- In: "my child comes out in hives whenever we visit my sister's house"
- Near-miss: "my throat is closing up and I can't breathe" → EMERGENCY prefilter
- Near-miss: "dry itchy patches with no obvious trigger" → dermatology

### rheumatology
**Scope:** Autoimmune and inflammatory joint and connective tissue disease: multi-joint, symmetrical, prolonged morning stiffness.
- In: "several joints stiff for over an hour every morning"
- In: "my fingers and wrists have been swollen and painful for months"
- In: "I was told I have lupus and need ongoing management"
- Near-miss: "one knee hurts after I run" → orthopedics
- Near-miss: "back pain since I lifted something heavy" → orthopedics

> Thin supply: 5 doctors. Retrieval falls back to `parent_bucket = general_medicine` when fewer than 2 results survive user filters. This does not affect classification.

### nutrition
**Scope:** Diet, weight management, sports and clinical nutrition, feeding advice. Self-referred lifestyle requests.
- In: "I want to lose weight, where do I start"
- In: "I need a diet plan that works with my diabetes"
- In: "my 5 year old refuses to eat anything but rice"
- Near-miss: "gaining weight despite eating very little, always cold and tired" → endocrinology
- Near-miss: "I've lost weight without trying to" → general_medicine

> **SAFETY:** Text suggesting disordered eating (restriction, purging, calorie targets, body-image distress) must not be routed to a dietician listing as if it were a weight-loss request. Needs its own handling path. Unintentional weight loss is a medical red flag, never a nutrition request.

---

## 3. Tie-break rules

These exist because the boundary is genuinely ambiguous and consistency matters more than correctness. Apply mechanically. Do not re-decide case by case.

**3.1 Child with a clear organ system** → route to the organ-system bucket, set the pediatric filter. Only route to `pediatrics` when there is no clear system, or the complaint is about general child health, growth, feeding, or development.

**3.2 orthopedics vs physiotherapy** → acute injury, trauma, or structural complaint goes to orthopedics. Ongoing rehabilitation, posture, movement retraining, or "I was told to do exercises" goes to physiotherapy. "Back pain after lifting something heavy" is a coin flip: assign **orthopedics** by rule.

**3.3 dermatology vs plastic_aesthetic** → if the user describes a symptom or a change, dermatology. If the user describes a desired appearance outcome, plastic_aesthetic. "Hair falling out" is dermatology; "hair transplant" is plastic_aesthetic.

**3.4 dentistry_general vs periodontics** → tooth structure to dentistry_general, gum and supporting tissue to periodontics.

**3.5 general_medicine as gravity well** → only assign when there is genuinely no dominant system. If a single system is named or clearly implied, use that bucket. Track general_medicine prediction rate as a separate metric alongside accuracy.

**3.6 Lower urinary symptoms in women** → urology by rule, even though a UAE patient might realistically see an OB/GYN. Chosen for consistency.

**3.7 rheumatology vs orthopedics** → multiple joints, symmetrical, or prolonged morning stiffness goes to rheumatology. Single joint, or clear mechanical or injury cause, goes to orthopedics.

**3.8 pulmonology vs cardiology for breathlessness** → wheeze, cough, or sputum goes to pulmonology. Ankle swelling, exertional chest tightness, or palpitations goes to cardiology.

**3.9 ent vs allergy_immunology** → seasonal, trigger-linked, or with itchy eyes goes to allergy_immunology. Structural, unilateral, persistent, or with hearing or voice change goes to ent.

**3.10 Ambiguous by design** → the product returns top-3 buckets. The eval set still records exactly ONE gold label per item, chosen by these rules. Top-3 accuracy is reported as a secondary metric.

---

## 4. Excluded from the label space

Retained in the mapping table, never a classifier output.

| Group | Doctors | Reason |
|---|---|---|
| `emergency` | 7 | Pre-filter, runs before classification. Asymmetric cost, tuned for recall. |
| `not_routable` | 114 | Radiology, pathology, anaesthesia, critical care, genetics, palliative, public health. Requires a prior clinical decision or specimen. Nobody self-refers. |
| `oncology` | 58 | **OPEN DECISION.** Entry is by referral or diagnosis, not by symptom text. Confirm before freezing. |
| `alternative_medicine` | 11 | Homeopathy, Hijama, Unani, Acupuncture. A modality preference, not a symptom destination. Surface as a user filter. |
| `unknown` | 11 | `nil` (8) and `Speciality 11` (3). Data quality issue, investigate separately. |

### Emergency prefilter triggers
Non-exhaustive, high recall by design, runs before the classifier:
chest pain or pressure, especially radiating; difficulty breathing now; severe or uncontrolled bleeding; sudden weakness or numbness on one side, facial droop, slurred speech; sudden severe headache; sudden vision loss; loss of consciousness; seizure; severe abdominal pain with rigidity or fever; throat closing or facial swelling; suspected poisoning or overdose; major trauma.

Output is "seek emergency care immediately", not a doctor listing.

---

## 5. Standard disclaimer

Attach to every user-facing routing output:

> This tool suggests which type of specialist may be appropriate based on what you described. It is not a diagnosis and does not replace medical advice. If your symptoms are severe or worsening, seek medical care immediately.

---

## 6. Change control

Taxonomy and definitions freeze together with the eval set. If a boundary is revised after any model has run, the eval set is re-labelled and every prior experiment re-run under v2, and that is reported.

Permitted exception: a boundary found unlabellable during eval-set construction, before any model has seen the data.
