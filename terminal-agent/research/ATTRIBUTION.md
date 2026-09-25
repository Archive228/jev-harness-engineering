# Sources and limits of the port

The agent uses its own Python/Textual runtime and small, explicitly marked
adaptations of open-source code. The original files, licences and descriptions of
the changes are kept next to the implementation. This is not a full fork of
another agent.

## What was actually ported

- **OpenCode, MIT.** From
  [`question.shared.ts`](https://github.com/anomalyco/opencode/blob/d870e22c70f27103016dcd479edcfebf86136d93/packages/opencode/src/cli/cmd/run/question.shared.ts)
  the state model and the transitions of the question flow were ported to
  Python: changing the request, selecting an option, writing your own answer,
  navigation, saving and sending. Runtime:
  [`question_state.py`](../jev_agent/question_state.py). In our adaptation only
  single-choice selection is supported, answers are always reviewed before
  submit, and an empty answer does not allow continuing. The original TypeScript
  is not executed.
  [Source, MIT and the differences](../vendor/opencode/PROVENANCE.md).
- **Hermes, MIT.** The structure of the `mark_recommended` and
  `strip_recommended` functions from
  [`tools/clarify_tool.py`](https://github.com/NousResearch/hermes-agent/blob/c1c84ea37f9cfee75a1bf8326b5597959c7ba499/tools/clarify_tool.py)
  is adapted in [`choice_labels.py`](../jev_agent/choice_labels.py): the marker
  is localised, and the original answer values are separated from the display
  text. The full vendored module serves as a record of provenance and is not
  imported into the product. The Hermes callback system, registry and timeout
  behaviour were not ported.
  [Source, MIT and the differences](../vendor/hermes/README.md).
- **OpenAI Codex, Apache-2.0.** In
  [`prompts/intake.md`](../jev_agent/prompts/intake.md) we adapted the planning
  sequence, the separation of project facts from user preferences, and the rules
  for questions and for revising the plan, from the open-source `plan.md` and
  `request_user_input_spec.rs`. Our own JSON contract is used. The Rust code and
  the app-server schemas are kept so the source can be checked and are not
  executed. The original `LICENSE`, `NOTICE`, hashes and pinned links are in
  `vendor/codex/`.
  [Sources and the differences](../vendor/codex/ADAPTATIONS.md).

[`intake_widgets.py`](../jev_agent/intake_widgets.py) connects the adapted
transitions to our Textual interface. It does not pull in OpenTUI, the Hermes
interface or a second agent runtime. Building the task, storing the version and
the transition to execution are implemented in
[`intake.py`](../jev_agent/intake.py).

## What served as a research source

- **Pi**: one mutable card per tool call ID, separate events for start, update
  and finish; expandable output; the separation of durable history from the UI.
- **PiJev**: a shortlist of real sources → Noul relevance; diagnosing errors
  with a bounded decision; assist/observe/off; an advisory error is not passed
  off as an answer from Jev.
- **OpenCode**: besides the port described above, the main conversation
  screen, searching commands and sessions, saving the draft and compact tool
  details.
- **Crush**: we studied the UX principles for the command and its output, for
  cancelling and for picking a session. No program code was ported. Its current
  licence is FSL-1.1-MIT, not MIT.
- **Claude Code**: the official documentation and an engineering description of
  `AskUserQuestion` helped separate the question flow from accepting the plan.
  The closed terminal implementation was not copied. Links to the primary
  sources and the limits of the conclusions are in
  [interaction-intake.md](./interaction-intake.md).

Versions and licences are pinned in [upstreams.json](./upstreams.json).
`vendor/` holds the exact sources of the adaptations actually used and their
licence notices. `research/licenses/` also keeps the licences of references
studied earlier; that does not mean code was ported from every one of them.

A full review of the flows with permanent links to specific files:
[the general audit](./upstream-audit.md), [engine](./engine-upstream.md),
[the terminal interface of the previous version](./ui-upstream.md),
[questions and plan](./interaction-intake.md), [Hermes](./hermes-intake.md),
[Codex](./codex-intake.md). The earlier reports record the state before the
current port. The current attribution is the one given here.

Not carried over automatically: the extension marketplace, the MCP runtime,
automatic compaction of the model context, session branching and several
generation providers. These features are tied to internal upstream protocols and
need a separate adapter and verification. Keeping the text history on our side
does not mean restoring every internal message of a separate Codex exec.
