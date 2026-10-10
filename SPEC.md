# RedPen — SPEC (v0.1, 2026-10-10, written during Banana Hacks 2026)

## 0. One line
A student photographs their handwritten algebra work and gets **their own page back, marked up like a teacher's red pen**: ticks on lines that hold, a circle on the first line that breaks, and a short margin hint written in handwriting. It never writes the answer.
Essence: *not* "an app that solves math from a photo" (Photomath) but "an image of **your** work with the **first slip** marked".

## 1. Success conditions (numbers) · deadline · non-goals
- S1 Verifier: on a deterministic seeded set (≥300 solutions, one injected error each + ≥100 error-free), FirstSlip line accuracy ≥ 95 %, false alarm on error-free ≤ 2 %.
- S2 End-to-end on synthetic handwritten pages (real human glyph strokes from Google MathWriting, several pseudo-writers, paper texture + rotation + blur): report FirstSlip accuracy **as measured** (target ≥ 70 %) and the share of pages where a misread was flagged as "unreadable" instead of a false "wrong".
- S3 Line segmentation: IoU ≥ 0.5 for ≥ 90 % of ground-truth lines on the synthetic pages.
- S4 One vision call per photo; p50 latency ≤ 10 s on the hosted demo.
- S5 Hosted demo works with zero setup: 3 sample pages render a marked-up image in ≤ 3 s without any model call (recorded readings).
- Deadline: v1 2026-10-11 20:00 KST; Devpost closes 2026-10-11 23:59 EDT.
- Non-goals: solving or showing answers; geometry/diagrams; calculus/matrices (reported as `unsupported`, never "wrong"); training or fine-tuning any model; accounts or storage of photos.

## 2. Constraints
- Hackathon rules (verbatim): "Your code goes in a public GitHub repo, committed inside the hacking window." · "Open-source libraries, public APIs, and pre-trained models are all fair game. Cite them in your README." · "Generative AI tools are allowed and encouraged. Just say which ones you used when you submit."
- Data: Google MathWriting glyph strokes, CC BY-NC-SA 4.0 — attribution in README, the derived glyph file keeps the same license, non-commercial use only.
- Cost: zero. Vision model = Gemini free tier (key server-side only). Photos are processed in memory and not stored.

## 3. Ubiquitous language (code names 1:1)
| Term | Meaning | Code |
|---|---|---|
| Page | the uploaded photo | `Page` |
| LineBox | a rectangle around one written line (pixels) | `LineBox` |
| Reading | transcription of one LineBox + confidence | `Reading` |
| Step | one line of work: index, text, box, confidence | `Step` |
| StepRelation | relation of a step to the previous one: `equivalent`, `not_equivalent`, `unreadable`, `unsupported`, `start` | `Relation` |
| FirstSlip | first step whose relation is `not_equivalent` | `Verdict.first_slip` |
| Hint | hint category, never the answer: `sign`, `arithmetic`, `distribution`, `dropped_term`, `lost_solution`, `extra_solution`, `check_step` | `Hint` |
| Verdict | relations for all steps + FirstSlip + Hint | `Verdict` |
| Mark | one red-pen stroke group: `tick`, `circle`, `note`, `query`, `summary` | `Mark` |
| MarkupPlan | ordered Marks anchored to LineBoxes | `MarkupPlan` |

## 4. Domain model
- `domain/algebra.py`: parse a Step's text into an equation / expression; relate two steps; classify the Hint. Pure Python + SymPy (a math library, no I/O).
- `domain/verdict.py`: `judge(steps) -> Verdict` (FirstSlip = first `not_equivalent`; `unreadable` steps are skipped and the next readable step is compared with the last readable one).
- `domain/markup.py`: `plan_markup(steps, verdict) -> MarkupPlan`.
- Ports (application): `LineSegmenter(page) -> [LineBox]`, `Transcriber(page, boxes) -> [Reading]`, `MarkupRenderer(page, plan) -> bytes`.

## 5. Use cases
| UC | Input | Output | Rule |
|---|---|---|---|
| UC-1 GradePage | photo bytes | Steps, Verdict, MarkupPlan, marked PNG | segment → one vision call → judge → render |
| UC-2 Regrade | photo bytes + edited Step texts (boxes kept) | same as UC-1 | **no vision call** |
| UC-3 Sample | sample id | same as UC-1 | recorded Readings, no vision call |

## 6. Acceptance criteria (each → ≥1 test)
- AC-1 Given steps `2x+3=7 / 2x=10 / x=5` When judged Then FirstSlip = step 2, Hint = `sign` (the +3 crossed the equals sign without flipping), step 3 relation = `equivalent` (carried error is not a second slip).
- AC-2 Given all steps equivalent When judged Then FirstSlip = None and the plan has one tick per step and a `summary` mark.
- AC-3 Given step 2 has confidence below threshold When judged Then step 2 = `unreadable`, it is not a FirstSlip candidate, and step 3 is compared with step 1.
- AC-4 Given a step containing an integral or a matrix When judged Then relation = `unsupported`, no exception, never `not_equivalent`.
- AC-5 Given the user edits a step's text When regraded Then the Transcriber is not called and the Verdict is recomputed.
- AC-6 Given `3x-5=10 / 3x=5` When judged Then Hint = `sign`; `2x+3=7 / 2x=5` → `arithmetic`; `2(x+3)=10 / 2x+3=10` → `distribution`; `x^2=3x / x=3` → `lost_solution`.
- AC-7 Given a malformed vision response (missing lines, bad JSON, extra ids) When transcribed Then affected lines become `unreadable`, no crash.
- AC-8 Given a synthetic page When segmented Then ≥90 % of ground-truth lines are matched with IoU ≥ 0.5.
- AC-9 Given a plan with a FirstSlip When rendered Then the output PNG has the same size as the input and red pixels appear inside the slip box's neighbourhood and nowhere over other lines' interiors.
- AC-10 The seeded-set eval meets S1 (CI gate).

- AC-11 Given the zoomed second reading of the slip line (or the line before it) differs from the first When graded Then the slip stands only if both readings break at the same line; otherwise the changed lines are `doubtful` (shown "?"), nothing is circled, and the chain restarts after them. (`tests/test_application.py`)
- AC-12 Given an answer check `3(5)-5=10` after a solved line `x=5` When judged Then it is `equivalent`; a false check is an `arithmetic` slip; `2x=4 → 0=0` is a slip. Rounded decimals are accepted to the precision written. (`tests/test_domain_judge.py`)
- AC-13 Given `=>`, `⇒`, `∴`, `→`, `therefore` before a line, `//` or `■` after it, or `v` between solutions When judged Then they are ignored / read as "or".
- AC-14 Given a slip When graded Then SymPy names the single written term that breaks the step (`Verdict.culprit`, never the corrected value) and the vision model is asked for its box inside the line; a box inside the line → only that term is circled, otherwise the whole line.
- AC-15 Given the student retyped a line When re-checked Then that line gets no tick on the old ink and the summary says "checks out as typed".
- AC-16 Given a read or re-read When the first model is silent for 7 s Then a backup model starts in parallel; each call has a 26 s deadline so a request stays under the 60 s platform limit.

## 7. Architecture (dependencies point inward)
```
redpen/domain/  ←  redpen/application/  ←  redpen/adapters/  ←  redpen/infrastructure/ (composition root, HTTP handler)
api/grade.py (Vercel entry) → redpen.infrastructure      public/ (static UI)      eval/ (seeded set, synthetic pages, runner)
```
- Adapters: `ProjectionSegmenter` (numpy/Pillow), `GeminiTranscriber` (set-of-mark prompt, JSON schema), `RecordedTranscriber` (samples, tests), `InkRenderer` (Pillow + MathWriting glyph strokes).

## 8. UI acceptance (Toss checklist, see design principle)
1 mobile first: 390 px no horizontal scroll, 1280 px intact · 2 one screen one question: upload → result · 3 type scale ≥22 px title / 16 px body / 13 px caption · 4 section gap ≥24 px, card radius ≥16 px, ≤1 shadow level · 5 one primary CTA fixed at bottom, ≥52 px, full width · 6 result card starts with the big number ("Line 3" or "4/4 steps hold") ≥28 px · 7 readings and maths details in `<details>` closed by default · 8 short friendly copy · 9 white + one accent + ok/warn/no, body contrast ≥4.5:1, dark mode basic · 10 no external fonts/CDN, skeleton while loading.

## 9. Physical verification
- Hosted URL: upload one synthetic page and one real photo from an openly licensed source; screenshot 390/1280; record latency.
- Eval numbers in README are produced by `python -m eval.run` and copied verbatim.

## 10. Change log
- v0.1 2026-10-10 first version (after opening ceremony).
- v0.2 2026-10-10 evening, after three rounds of mock judging: AC-11..AC-16. S4 revised: one read call + one confirm call + one pointing call per slipped page (measured 8–25 s end to end on the free tier).
