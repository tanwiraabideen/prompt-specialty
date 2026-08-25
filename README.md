# Symptom-to-specialty classifier

MyDrWorld is an application that allows users to find doctors in the UAE based on their desired criteria.

A lot of patients don't know what type of doctor they need to see in the first place.

I built a symptom-to-doctor classifier for them, that allows users to enter a prompt, and then they will be given a recommended specialty, and then recommended doctors.

I compared different models and setups, to see which would best benefit the company.

## Initial hurdles

- I had no data on search queries by patients, so I had to synthesize most of the data.
- The master specialty list has 285 specialties. A lot of these specialties are very similar to other specialties, or even just spelt differently.

## 1. Taxonomy design

- I created a many-to-one mapping. If a receptionist wouldn't reliably decide between multiple specialties, I decided that they are sub-specialties and they would map to one bucket. In the end I ended up with 24 buckets.
- I removed ~10% of the specialties as they were not physicians that a patient would refer to, for example a radiologist.
- Dentistry was a very large portion of the database (~20%), so I allocated 3 different buckets.

## 2. Evaluation design

- I didn't have any labeled data, so I used an LLM to synthesize the symptoms. The training and development sets were completely synthesized by an LLM. However for the evaluation set, I got 2 physicians to match the 325 synthesized symptoms to a bucket. I called this the gold labels.

## 3. Model selection

I decided to compare 3 different setups.

- The most basic setup predicts the most common class (`general_medicine`) for each symptom.
- I also implemented a zero-shot classification using GPT-5.6 Luna. I tested 3 different versions of this, with different system prompts. One version just gave the bucket names it can choose from, one version also gave a one-line scope for each bucket, and the final version on top of that had 2 example phrasings and a near-miss symptom.
- Finally I implemented a LoRA fine-tuned Llama-3.2 3B model, and also a 1B model. In the results I will compare the fine-tuned vs the original model.

## 4. Results

| System | Input tokens | Macro-F1 | Accuracy | Top-3 | Parse OK |
| --- | ---: | ---: | ---: | ---: | ---: |
| GPT-5.6 Luna, full definitions | 3,127 | 0.938 | 0.898 | 0.918 | 98% |
| GPT-5.6 Luna, scope lines only | 1,378 | 0.938 | 0.900 | 0.920 | 100% |
| GPT-5.6 Luna, bucket names only | 654 | 0.862 | 0.857 | 0.898 | 98% |
| Llama-3.2-3B + LoRA | 71 | 0.806 | 0.740 | n/a | 100% |
| Llama-3.2-3B, full definitions | 3,127 | 0.694 | 0.756 | 0.889 | 90% |
| Llama-3.2-3B, scope lines only | 1,378 | 0.495 | 0.563 | 0.813 | 96% |
| Llama-3.2-3B, bucket names only | 654 | 0.488 | 0.609 | 0.783 | 92% |
| Llama-3.2-1B, scope lines only | 1,378 | 0.221 | 0.271 | 0.583 | 96% |
| Llama-3.2-1B, bucket names only | 654 | 0.180 | 0.229 | 0.542 | 96% |
| Llama-3.2-1B, full definitions | 3,127 | 0.177 | 0.174 | 0.435 | 92% |
| Majority class | — | 0.002 | 0.020 | 0.020 | 100% |

- The Luna model actually did worse with the full definitions, showing that longer prompts can actually degrade quality.
- Fine tuning added 11 points to the original version of Llama-3.2 3B. It also increased the parse rate to 100%.
- For the fine-tuned model, macro-F1 increased whilst accuracy decreased. Showing that it performs better on the less common cases and slightly worse on the common ones.
- The fine-tuned model used 44x fewer tokens than the Luna model with full definitions.
- However for our application, accuracy is more important than latency, so for the shipped product I will be using GPT-5.6 Luna with scope lines as it's the best performing.

##5. Final Implementation

I implemented an emergency pre filter. For each symptom, it's sent to an LLM to see whether it can be classified as an emergency or not. I weighted it towards more likely to classify as emergency as failing to detect an emergency is much more dangerous than falsely detecting an emergency.

I then simply integrated the infrastructure with the web application.

