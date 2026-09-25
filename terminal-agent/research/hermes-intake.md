# Hermes: clarification, planning, and legible terminal state

Verified 21 September 2026. The official repository
[NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent), commit
`c1c84ea37f9cfee75a1bf8326b5597959c7ba499`. The repository was cloned and read;
its installers, CLI and model requests were not run. This examines specific code
paths, and is not a claim that the whole large project has been checked.

## What actually happens in Hermes

Clarification is a tool in its own right, `clarify`. It does not arise
automatically out of a good-looking window: the model has to call the tool with
its questions. The tool validates the data and passes it to the interface
callback; the interface returns structured answers, and the agent loop then
continues.

1. [`tools/clarify_tool.py:106–136`](https://github.com/NousResearch/hermes-agent/blob/c1c84ea37f9cfee75a1bf8326b5597959c7ba499/tools/clarify_tool.py#L106-L136)
   normalises the batch: up to five independent questions, up to four options per question.
   The wire ID is generated as `q0`, `q1` rather than taken from arbitrary model text.
   `choices_offered` holds the bare answers, `choices` holds the labels for display.
2. [`agent/inline_tool_executors.py:189–194`](https://github.com/NousResearch/hermes-agent/blob/c1c84ea37f9cfee75a1bf8326b5597959c7ba499/agent/inline_tool_executors.py#L189-L194)
   passes `agent.clarify_callback` to the tool. A call that asks a question is excluded
   from parallel tool execution: the ordinary tool-execution timer must not cut off a
   live dialogue with a person
   ([`agent/tool_executor.py:859–875`](https://github.com/NousResearch/hermes-agent/blob/c1c84ea37f9cfee75a1bf8326b5597959c7ba499/agent/tool_executor.py#L859-L875)).
3. In the Python CLI,
   [`_clarify_callback_batch`](https://github.com/NousResearch/hermes-agent/blob/c1c84ea37f9cfee75a1bf8326b5597959c7ba499/hermes_cli/cli_modal_mixin.py#L709-L744)
   creates `questions`, `answers`, `answer_meta`, `active` and the answer queue.
   The working thread waits; the terminal loop keeps accepting keystrokes.
4. [`_clarify_batch_set_active` / `_clarify_batch_lock`](https://github.com/NousResearch/hermes-agent/blob/c1c84ea37f9cfee75a1bf8326b5597959c7ba499/hermes_cli/cli_modal_mixin.py#L627-L707)
   restore the cursor and the text entered earlier when a question is revisited.
   Enter commits the answer and moves to the next unanswered question.
   Tab/Shift+Tab go back. `Other` opens free-text entry.
5. [`_get_clarify_batch_display_fragments`](https://github.com/NousResearch/hermes-agent/blob/c1c84ea37f9cfee75a1bf8326b5597959c7ba499/hermes_cli/cli_tui_mixin.py#L434-L507)
   shows the whole list of questions but expands the options only for the active one:
   an answered question is marked `✓`, the current one `▸`, a pending one `·`. The
   accepted answer is shown on a line of its own. The user can see how many are left.
6. [`_batch_result`](https://github.com/NousResearch/hermes-agent/blob/c1c84ea37f9cfee75a1bf8326b5597959c7ba499/tools/clarify_tool.py#L139-L185)
   returns the question, the options offered and the actual answer to the model loop.
   The recommendation marker is stripped: presentation does not stand in for the user's data.

The new separate Hermes shell is React/Ink, and Python remains the owner of the
model, the tools and the sessions. JSON-RPC over stdio sits between them. That is
a different stack, not Textual. The same data becomes an overlay in
[`createServerRequestHandler.ts:43–72`](https://github.com/NousResearch/hermes-agent/blob/c1c84ea37f9cfee75a1bf8326b5597959c7ba499/ui-tui/src/app/createServerRequestHandler.ts#L43-L72),
and the interactivity is implemented by
[`ClarifyPrompt`](https://github.com/NousResearch/hermes-agent/blob/c1c84ea37f9cfee75a1bf8326b5597959c7ba499/ui-tui/src/components/prompts.tsx#L143-L238).
Its answers are keyed to a request ID and a question ID; returning to a question
restores the selection. The [architecture description](https://github.com/NousResearch/hermes-agent/blob/c1c84ea37f9cfee75a1bf8326b5597959c7ba499/ui-tui/README.md#L1-L41)
is confirmed by the code, not by screenshots alone.

## A plan is not a list of animations

[`agent/plan_prompt.py:10–71`](https://github.com/NousResearch/hermes-agent/blob/c1c84ea37f9cfee75a1bf8326b5597959c7ba499/agent/plan_prompt.py#L10-L71)
builds an ordinary request: the goal, the context, the approach, specific files and
check commands, risks and open questions. Where something is uncertain, ask; where
the context is sufficient, produce a plan. In this implementation `/plan` is not a
separate reasoning engine: it is instructions to the existing agent. They forbid
execution apart from writing the plan out. The text of that prohibition is not
itself a filesystem sandbox.

[`tools/todo_tool.py:26–95`](https://github.com/NousResearch/hermes-agent/blob/c1c84ea37f9cfee75a1bf8326b5597959c7ba499/tools/todo_tool.py#L26-L95)
gives plan state that does not depend on how it is drawn: stable IDs, statuses, the
full state, and a new revision only on a real change. Reads return copies. After
context compaction the active items are fed back in so that the agent does not start
finished actions over again
([`format_for_injection`](https://github.com/NousResearch/hermes-agent/blob/c1c84ea37f9cfee75a1bf8326b5597959c7ba499/tools/todo_tool.py#L97-L126)).
This is a useful principle for our own future progress display: the plan and the
check on the result belong in state, and the terminal only shows them. The word
`completed`, arriving from the generator, is not yet evidence of a check.

## What was wrong in our own flow

Before intake was added, `Session._execute` took the user's original sentence, chose
between `implement/inspect/answer`, retrieved context and started the worker. The
instruction “If essential information is missing, ask one concise question.” lived
inside the worker prompt. The harness had no separate state for “we are waiting for an
answer to this question”, no assembled task and no explicit boundary between design and
execution. So a sentence like “Сделай что-нибудь про крипту” (“build me something about
crypto”) went down the same path as a precise task about CSV. That phrasing is the
fixture request in `tests/test_intake.py`; the intake tests use Russian user input, so
it is quoted as recorded rather than translated. Polishing the buttons does not fix
that defect.

The path we need: original idea → bounded clarification → goal, inputs, result and
readiness criteria → a plan a person can review at a glance → start. Jev receives a
task that is already assembled, instead of having to guess the product from a single
word. The generator writes the questions and the prose; Jev's typed decisions and the
Python harness keep the responsibilities they already have. Clear, simple requests
should not be forced through a pointless interview.

## What was actually ported

[`vendor/hermes`](../vendor/hermes/README.md) holds an **exact copy** of
`tools/clarify_tool.py`, the MIT licence and the SHA-256 hashes. The original module
is kept as a record of provenance and is not imported by the product.

[`jev_agent/choice_labels.py`](../jev_agent/choice_labels.py) adapts the code of
`mark_recommended` and `strip_recommended` from lines 35–49 of the original. The
changes: an English marker, reading the Russian marker as well, a fresh list for
display and a guard against an empty first option. The API uses the standard library
only, works on Python 3.9 and adds no dependencies. The recommendation label is
presentation only; the selected value stays as bare text.

[`tests/test_choice_labels.py`](../tests/test_choice_labels.py): five checks passed
locally. They cover that the input data is left unchanged, repeated decoration, both
languages, the empty and single-option cases, and the conversion back to a bare answer.
The command: `.venv/bin/python -B -m unittest discover -s tests -p test_choice_labels.py -v`.
The upstream tests were read, but its full test suite was not run here.

## What was deliberately not ported

- Upstream has a timeout that invites the agent to decide for itself
  ([`clarify_tool.py:11–14`](https://github.com/NousResearch/hermes-agent/blob/c1c84ea37f9cfee75a1bf8326b5597959c7ba499/tools/clarify_tool.py#L11-L14)).
  For accepting our plan, the absence of an answer does not mean consent. Closing the
  window, cancelling and an accepted answer have to be different states.
- We do not move a synchronous `queue.get()` onto the Textual thread. In Hermes it sits
  in the agent thread; in our case the same code would block the keyboard and redrawing.
- We do not retry the callback after a `TypeError`: Hermes checks the signature up front,
  because an error inside the callback would otherwise ask the question again.
- We do not copy Hermes' dynamic tool registration and we do not run the vendored
  source. The full upstream requires
  [Python >=3.11,<3.14](https://github.com/NousResearch/hermes-agent/blob/c1c84ea37f9cfee75a1bf8326b5597959c7ba499/pyproject.toml#L15),
  and some of our readers are on Python 3.9.
- We do not substitute the first “recommended” option for a refusal or an unknown answer.
  A recommendation should help a person choose, not quietly choose for them.
- We do not carry over the `/plan` requirement to commit at every step: it has nothing
  to do with the user's task and should not appear in our agent by itself.

The licence permits adaptation provided the copyright and the MIT notice are kept; both
are kept. The full Hermes terminal, its model loop and its tools are not claimed as our
code and are not included as a working dependency.
