# eval/results — which file is what
| File | What | Use |
|---|---|---|
| `synthetic-gemma-4-26b-a4b-it-n150.json` | 150 synthetic pages, current pipeline vs same model asked directly | **headline table in the README** |
| `synthetic-gemma-4-26b-a4b-it-n150-reasoned-baseline.json` | same 150 pages, baseline allowed to transcribe and reason step by step | stronger baseline |
| `real-gemma-4-26b-a4b-it.json` | 30 real answer-sheet crops (7 tuning + 23 held-out) | real-photo table |
| `synthetic-gemma-4-26b-a4b-it.json` | earlier 60-page run (before the answer-check / notation fixes) | history |
| `synthetic-gemma-4-31b-it.json` | first 4-page smoke test, before the read-twice rule (pipeline was worse than the baseline then) | history, kept on purpose |
| `*-noanswer-baseline.json` | same pages, reasoning baseline also told not to reveal the answer | stronger baseline 2 |
| `real-gemma-4-26b-a4b-it-frozen.json` | real crops scored with the rules as frozen before the held-out set was evaluated | held-out honesty |
| `*-answer-leak*.json` | does the baseline's explanation state the correct answer (automatic + hand-checked list) | answer-leak claim |
