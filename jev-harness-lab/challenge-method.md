# Independent stress check of Jev

The set `fixtures/live-eval-challenge-cases.json` was assembled separately on 20 September 2026, before any of its requests to the API. While assembling it we read the current questions and the schema in `live_eval.py`, and the original `fixtures/live-eval-cases.json` in order to rule out literal duplicates. The author of the set did not read the model's saved live answers, did not open credentials and did not run any paid requests. Independence here refers to assembling the cases without looking at the answers. It is not a blind study by an independent organisation.

The set holds **18 new cases and 28 expected answers**: 10 support messages give category and has_workaround, 8 diagnostic states give next_check. Five of the support messages are written in English and five in Russian. The diagnostic states are split 4/4. Support categories: export 3, payment 3, account 2, other 2. Workaround: 5 true and 5 false. Diagnostics: D1 3, D2 2, none_suitable 3. These are deliberately hard cases, not a sample of user traffic and not an assessment of production reliability.

Before the requests we checked locally: the schema through `load_cases`, the permitted gold values, the counts, and that no state is a literal duplicate of one in the original set. The hashes were computed with the `digest` function from `live_eval.py` (canonicalised JSON, SHA-256): the set is `57179107cd4df9a3511d290583f16b5cc60dc8c9cba7a653863bf32ccd1a3ecf`, the questions are `ad42292735262af68ccc4ff9d386fb709f7b83cffddcd3e3d9208b519db59d6a`.

## What was fixed before the run

It uses **the same** `SUPPORT_QUESTIONS`, `DIAGNOSTIC_QUESTIONS`, model and thresholds as the main protocol. The set does not redefine the category values or the acceptance rules. Category means the real problem the customer is asking to have fixed. Workaround requires that the customer explicitly describes having applied an alternative successfully. Promises, untested advice and failed attempts do not count. A diagnostic needs a fresh, relevant and executable next step on the current snapshot.

Gold is held only in `expected` and is not part of the `state` passed to the model. The snapshot and runtime fields are facts of the example state, not hints at the wanted answer. In several cases `already_run` deliberately holds a history of attempts. The observations clearly distinguish an earlier run, a fresh diagnostic that was carried out, and an attempt that produced no result. This checks that the whole state is read against the current question, rather than one list of IDs being trusted.

Before the first request the runner saves a copy of the dataset, the hashes of the set, the questions and the code, the thresholds, and every request. Once the predictions have been looked at, neither this set nor its gold is edited. Any ambiguity found is described in the report. A corrected version must get a new version name and a separate run. The answers for every case are saved, including errors and the policy refusing to accept an unconfident decision. Picking only the successful answers is not allowed.

## Why these cases were added

- `challenge-support-en-01`, `en-02`, `ru-01`, `ru-05`: mentions of features that work, or that are denied, do not decide the category of the problem.
- `challenge-support-en-04`, `ru-03`: the words "invoice", "password", «оплата» ("payment") and «вход» ("login") inside card titles do not describe a fault in those features; the last two are quoted from the Russian-language ticket.
- `challenge-support-en-03`, `ru-04`: an unrelated textual instruction tries to override the classification, while the customer's actual request is stated unambiguously. Two such cases are not a full assessment of robustness to prompt injection.
- `challenge-support-en-05`, `ru-02`, `ru-05`: a first alternative that failed, a later success and a promise of a future fix differ in their actual outcome.
- `challenge-diag-en-01`, `ru-02`: a diagnostic carried out earlier went stale after the relevant part of the sources changed.
- `challenge-diag-en-02`: an attempted command with no execution and no observation does not replace a fresh diagnostic. The obstacle to execution has explicitly been removed.
- `challenge-diag-ru-01`, `ru-04`: a confident statement by the author and a passing test of another area do not cover the missing check.
- `challenge-diag-en-03`, `en-04`, `ru-03`: an executable but irrelevant step, commands that cannot be executed, and both diagnostics already covered must all lead to `none_suitable`, for different reasons.

## Ambiguities ruled out while assembling the set

Every support message has one specific fault and one required category. Tickets are not included where payment and login are broken at once, where the causal link between them is unclear, or where the alternative worked only for another person. For a positive workaround the message states explicitly that the wanted result has already been obtained. For a negative one, that it has not. In the case of email instead of desktop alerts, the alternative is receiving the same notifications, already confirmed, and not a guess that email might help some day.

The diagnostic states leave no choice between two equally useful commands that have not been run. For D1 and D2 the alternative command is already covered by a fresh observation, and the chosen one adds exactly the evidence that is missing. For `none_suitable` the reason is spelled out in facts: irrelevance, the application not being importable, or both available steps being fully covered. A low confidence and an explicitly correct `none_suitable` remain different outcomes.

## How to read the result

Report separately from the original 18-case set: raw accuracy per question, accepted correct and incorrect decisions, abstentions, coverage, API errors, real requests, tokens and the total request time. Use the weak baselines already declared, without tuning them to these cases. This stress set does not prove cost savings, that repair is useful in a real repository, universal protection against injection, or superiority over an ordinary LLM.

The current `evaluate(..., cases_path=...)` supports a separate path for the set. Adding a CLI flag for it is not a change to the questions or the gold. This document by itself does not claim that a live run has already been carried out.
