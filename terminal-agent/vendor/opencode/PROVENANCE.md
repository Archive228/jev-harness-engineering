# OpenCode question state machine

Repository: https://github.com/anomalyco/opencode

Pinned commit: `d870e22c70f27103016dcd479edcfebf86136d93`

Original: [`packages/opencode/src/cli/cmd/run/question.shared.ts`](https://github.com/anomalyco/opencode/blob/d870e22c70f27103016dcd479edcfebf86136d93/packages/opencode/src/cli/cmd/run/question.shared.ts)

`question.shared.ts` is an exact source copy for provenance. It is not executed or
imported. `LICENSE` is the upstream MIT notice, copyright (c) 2025 opencode.

`jev_agent/question_state.py` is a Python adaptation of the pure state model and
its sync, tab, selection, custom-answer, move, pick, save, submit and reject
transitions. No Solid/OpenTUI runtime is included. Changes:

- Single-choice intake only; unsupported multi-select behavior is not exposed.
- All question counts include a review stage; selecting one answer never starts
  work or implicitly approves a plan.
- Empty answers block submission; empty custom text does not advance.
- Draft text and selected answers remain separate, and returned collections are
  copied so UI edits do not modify the previous state.
- Stable question IDs map positional internal answers to the session API.

`jev_agent/intake_widgets.py` is our Textual renderer. Its keyboard-first choice,
custom answer and review interaction follows the upstream design; its layout and
plan screen are project-specific. Tests exercise upstream-equivalent transitions
and our additional review, persistence, multiline and compact-layout behavior.
