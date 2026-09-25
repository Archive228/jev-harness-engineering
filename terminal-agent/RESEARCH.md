# Why the terminal agent is built this way

Verified on 20 September 2026 against the TypeSafe documentation, the source projects and our lab's materials. This is the rationale for the design, and the actual results of a particular run sit in that run's log.

## Two different kinds of work

The user writes an ordinary task. The generative worker reads the project, makes a plan, writes code and answers in words. Jev receives a short description of the current state and answers specific questions: which direction fits, whether a result relates to the request, whether the attached facts are sufficient for a specific statement. The program ties these answers to execution and records events.

```text
request → generative worker → files, commands, observations
                                ↓
                       Jev: typed answers
                                ↓
                   code: continue, check, stop
```

Jev does not generate free text. A plan, program code and conversation need a generative component. TypeSafe states this limit outright, and LangChain suggests pairing Jev with the model that drives the agent. [Jev 1.13: limitations](https://docs.typesafe.ai/model-jaggedness/jev-1.13), [Building a Harness with Jev](https://www.langchain.com/blog/building-a-harness-with-jev).

## What can be handed to Jev

- **Choice** picks one option from an explicit list. It fits the direction of work, or picking the next available diagnostic. If no suitable option may exist, `none_suitable` is required.
- **Noul** judges the probability of one specific statement. For example: "Does the attached check output support the statement about search by description?"
- **Score** judges one described scale. It is not a counter of completed work, and not a way to compute an exact number.

The questions inside one request are evaluated independently and do not receive the answers of neighbouring questions. If a tool brought new facts, judging those facts needs a new request. A question's field name does not stand in for its full `instructions`: the model does not see the question ID. [The official TypeSafe skill](https://github.com/typesafe-ai/skills/blob/main/skills/typesafe-ai/SKILL.md), [Choice](https://docs.typesafe.ai/primitives/choice).

When choosing an action we describe the options actually available. When checking a statement we pass the statement itself and the observations that relate to it. A whole repository, or a long unfiltered log, adds noise. Arithmetic, exit codes, deadlines, limits and the comparison of file snapshots are computed by code. [Jev 1.13: limitations](https://docs.typesafe.ai/model-jaggedness/jev-1.13).

## What the bars and statuses mean

`probabilities` and `confidence` are taken from the service response. The maximum probability and confidence are different fields. The official confidence page publishes no universal formula for deriving it from `p_max`, and the interface must not present such a formula as the API contract. The threshold belongs to our policy and needs checking on the class of tasks you care about. [Confidence](https://docs.typesafe.ai/confidence).

The worker process finishing, a passing test and acceptance of the whole task are different facts. The model's message "done" does not stand in for command results. A high Jev judgement is not independent evidence of correctness either. An explicitly stated contract needs fresh checks of the current result. For a free-form task the report lists the artifacts created and the checks actually run, and keeps unverified claims separate.

The graph in the terminal shows observable stages, calls, commands and the program's transitions. It is a log of the work, not a visualisation of the model's internal reasoning. A recorded run must be marked as replay, and fixtures as demo. A live request must have its own API responses, timestamps and result.

## Where the useful constructs come from

- [Function calling](https://docs.typesafe.ai/cookbooks/function_calling): picking a handler and its arguments from closed sets, with execution left to ordinary code.
- [Skill suggestion](https://docs.typesafe.ai/cookbooks/skill_suggestion): ranking candidates, then checking the short list with the option to reject every candidate. It is an example of extending an agent, not a promise of a built-in skills library.
- [Foreman](https://github.com/thruwire/foreman): a separate generative worker and semantic supervisor, a bounded action policy, observations and an event log. It is a third-party architectural experiment. Its authors describe [the limits of the proof](https://github.com/thruwire/foreman/blob/main/docs/what-foreman-proves.md) separately, and a successful demo does not establish general reliability or an advantage over other agents.
- [Our source verification](../source-check.md) and [the lab](../jev-harness-lab/README.md): an API contract already tested, saving of requests and answers, freshness checks on facts, and explicit stop reasons. The older `jev-console.html` shows saved runs. The new user request needs an interactive terminal run on a task typed in.

The new terminal develops these constructs. The links mark where the architectural decisions came from, not a claim that third-party authors reviewed our implementation.

Multi-line input uses the stock [TextArea](https://textual.textualize.io/widgets/text_area/) of the pinned Textual 0.89.1: a paste stays text, and sending is moved to Ctrl+D and a separate button.
