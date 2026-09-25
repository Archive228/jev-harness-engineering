# Source verification for the full Jev article

The contract was verified against primary sources on 19 and 20 September 2026. This note describes where the technical claims come from. Live calls, the labelled sets and the full Jev + Codex loop were run separately on 20 September; their actual results are in [VALIDATION.md](./VALIDATION.md).

## The contract we use in the code

The correct documentation address is [API reference](https://docs.typesafe.ai/api). The address `/api-reference/system-one` did not open. The request: `POST https://api.typesafe.ai/v1/systemone`, with the headers `Authorization: Bearer …` and `Content-Type: application/json`.

The body contains `state`, `model` and `questions`. `state` accepts a string, an object or an array. `questions` is an object with IDs the developer picks; the answer comes back under those same IDs. The model does not see the question IDs themselves, so the meaning of the condition has to sit in `instructions` and not in the field name alone. The answer contains `model`, `answers`, `usage.input_tokens` and `usage.output_tokens`. API errors include 401, 422, 429 and 529; the last two require a delay before a retry. In a teaching client a bounded retry or an explicitly recorded stop is acceptable, but an error never turns into a positive judgement.

### Choice

The question contains `type: "choice"`, `instructions` and `criteria`, a dictionary of options. In our implementation the descriptions are strings: that is compatible with the API reference and with the primitive's page. The answer contains `type`, `choice`, `probabilities` and `confidence`. `choice` names the option with the highest probability; the distribution includes every option. It helps to add `none_suitable` when there may be no fitting option. [Choice](https://docs.typesafe.ai/primitives/choice).

### Score

The question contains `type: "score"`, `instructions` and an ordered array of level descriptions in `criteria`; from 2 to 10 levels. The answer contains `type`, `score`, `legend`, `probabilities` and `confidence`. In the HTTP JSON the keys of `legend` and `probabilities` are the strings `"0"`, `"1"` and onward. `score` equals the sum of each level index multiplied by its probability. It is a position on the scale you defined; a fractional result does not mean a percentage of users and does not certify that the decision is correct. Do not turn the scale into a way of computing exact physical or monetary quantities. [Score](https://docs.typesafe.ai/primitives/score).

### Noul

The question contains `type: "noul"`, `instructions` and, where needed, `criteria` with the string keys `"true"` and `"false"` whose values are descriptions. The answer: `type` and `noul`. A value from 0 to 1 expresses the probability of "yes"; there is no separate `confidence`. A value near 0.5 means the probabilities of "yes" and "no" are close, not that the property is present to a middling degree. [Noul](https://docs.typesafe.ai/primitives/noul).

### Confidence

This is a computed property of the Choice and Score distribution. The documentation explains the link to how concentrated the probabilities are, but the page we checked does not publish the exact formula. You cannot present the maximum probability as a `confidence` identically equal to it, invent a formula, or read the value as accuracy proven on our set. A threshold is chosen and checked for one specific action. Invented demo answers have to be labelled as fixtures, with no claim that the service will return such numbers. [Confidence](https://docs.typesafe.ai/confidence).

## The model and where it applies

For a reproducible example `jev-1.13.0` is the right choice: [Models](https://docs.typesafe.ai/models) lists that version as current. `jev-latest` and `jev-preview` point at it today, but they change independently of the client code. Versioned IDs are accepted even when `GET /v1/models` lists only aliases. The model accepts text and structured textual state; images, audio and video need another handler first. English is listed as the main training language; Russian examples have to be checked separately. Where the article did not measure latency and cost, do not promise the reader a specific speed-up or saving factor.

Within one call the questions judge one state independently. Inside that call neither a question nor an answer receives the results of a neighbouring question. Code combines the answers. When the next set of options depends on the previous decision or on a tool result, you need a new request. [Primitives](https://docs.typesafe.ai/primitives), [Speculative fan-out](https://docs.typesafe.ai/patterns/fan-out).

The article's explanation should stay at the level of the contract: state → questions → typed answers → an action by the program. The sources we checked give no grounds for drawing a specific internal encoder/decoder architecture or a number of passes, and none for claiming that ordinary LLMs cannot do structured output. [TypeSafe introduction](https://docs.typesafe.ai/introduction).

For Jev 1.13 the vendor lists errors of literal reading, of counting and arithmetic, of date comparison, of multi-step conditions, of irrelevant context, of contradictory criteria, and the influence of deliberately misleading state. Related questions are not obliged to respect the arithmetic identities you would expect between them. This supports our implementation: code computes the facts of execution and the limits; the model judges one narrow semantic question; passed/failed/unverified are not replaced by an arbitrary general "readiness". [Jev 1.13 jaggedness](https://docs.typesafe.ai/model-jaggedness/jev-1.13).

## What external projects confirm

LangChain describes `TypeSafeClassifier` as an integration for typed classifications. There are experimental `ModelRouterMiddleware` and `AutoModeMiddleware`; the latter blocks risky calls to the tools it lists, and does not itself organise a request for permission. These are examples of places to plug Jev in, not measured proof that a full harness succeeds. The article was published on 17 September 2026. [LangChain's write-up](https://www.langchain.com/blog/building-a-harness-with-jev), [integration documentation](https://docs.langchain.com/oss/python/integrations/providers/typesafe).

Foreman shows an architecture of parallel coding workers and a supervisor, nine Noul judgements and a programmatic transition policy. The authors draw an explicit line between the architecture working and the quality of Jev's judgements. The deterministic demo checks runtime properties; a real integration needs access to external services. The repository does not establish an improvement in success rate, cost or latency, and does not claim that `FINISH` guarantees the program is correct. [Foreman](https://github.com/thruwire/foreman), [the limits of the proof](https://github.com/thruwire/foreman/blob/main/docs/what-foreman-proves.md).

## Editorial limits on our results

Our offline demo shows that commands run, that reports are produced, that a failing test blocks completion, that limits stop the loop, and that replay notices a divergence in actions. Jev's quality was checked separately on two sets of our own of 18 states each; the whole chain was checked on three prepared defects with an independent final acceptance. Every case is saved, including the stop on confidence and the separate recovery. These small experiments do not establish the model's general reliability, the quality of its calibration, or an advantage over a fixed order and a strong LLM baseline.

## Official open-source implementations

- [TypeSafe skills](https://github.com/typesafe-ai/skills): the useful pattern here is independent questions in one request, and a new request once there are new facts. [MIT license](https://github.com/typesafe-ai/skills/blob/main/LICENSE).
- [Python SDK](https://github.com/typesafe-ai/typesafe-sdk-python): typed answers, explicit retries and a request identifier for diagnosing an error. Our small REST client keeps the absence of hidden retries, a shared deadline, and a safe request ID when the server returns one. [MIT license](https://github.com/typesafe-ai/typesafe-sdk-python/blob/main/LICENSE).
- [System One Adapter](https://github.com/typesafe-ai/system-one-adapter-python): a route to a separate comparison against an ordinary LLM, including counting every attempt. Such an LLM baseline is not part of the experiments this article ran. [MIT license](https://github.com/typesafe-ai/system-one-adapter-python/blob/main/LICENSE).

No third-party source code was copied into the lab; the links mark the sources of the method and the interface.
