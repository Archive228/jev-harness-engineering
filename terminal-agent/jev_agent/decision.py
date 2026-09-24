"""Turn policy as data and one pure function, so a decision can be replayed.

Every threshold that decides a turn lives here, not inline in the executor, and
every decision is a function of recorded inputs alone: no I/O, no clock, no
model call. A saved turn can therefore be re-decided from its journal, and a
threshold change can be measured against history before it is applied.

POLICY_VERSION must be raised whenever a threshold or a rule changes, because a
recorded decision is only comparable to a recomputed one under the same policy.
"""

POLICY_VERSION = 3

# Thresholds are data, not literals in the executor. Each one is named after the
# decision it gates so that a verdict can report which bar actually applied.
THRESHOLDS = {
    # Attempts of the worker inside one turn.
    "max_attempts": 3,
    # Below this Choice confidence the route is not trusted with file changes.
    "route_min_confidence": 0.25,
    # Triage advice is only forwarded to the worker above both bars.
    "triage_min_confidence": 0.55,
    "triage_min_probability": 0.65,
    # "improve" is only acted on above this bar; below it the turn asks the user.
    "improve_min_confidence": 0.6,
    # Below this the observed work is not considered to answer the request.
    "addresses_request_min_noul": 0.5,
    # Below this one requirement of the approved plan counts as still open. This
    # bar names what to work on next; it does not decide acceptance, because a
    # plan requirement is prose, not an executed check.
    "requirement_closed_min_noul": 0.5,
}

# How the judge participated in this decision. The distinction matters: a judge
# that was never consulted (observe/off) leaves the decision to Python policy,
# while a judge that was consulted and failed must not be read as agreement.
JUDGE_STATES = ("applied", "not_consulted", "unavailable")


def thresholds(overrides=None):
    """A validated copy of the policy. Unknown names are rejected, not ignored."""
    values = dict(THRESHOLDS)
    for name, value in (overrides or {}).items():
        if name not in THRESHOLDS:
            raise ValueError("Unknown policy threshold: " + str(name))
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("Threshold %s must be a number." % name)
        if name == "max_attempts":
            if int(value) != value or value < 1:
                raise ValueError("max_attempts must be an integer of at least 1.")
            values[name] = int(value)
            continue
        if not 0.0 <= float(value) <= 1.0:
            raise ValueError("Threshold %s must lie in the range 0..1." % name)
        values[name] = float(value)
    return values


def route_uncertain(confidence, policy=None):
    """True when the routing answer is too weak to authorise file changes."""
    policy = thresholds() if policy is None else policy
    return confidence < policy["route_min_confidence"]


def triage_applies(answer, policy=None):
    """True when a triage category is confident enough to reach the worker."""
    policy = thresholds() if policy is None else policy
    return (answer["confidence"] >= policy["triage_min_confidence"]
            and answer["probabilities"][answer["choice"]] >= policy["triage_min_probability"])


def requirement_gaps(answers, requirements, policy=None):
    """Which approved requirements the observed work has not shown closed.

    Advisory by construction: it says what the next attempt should address, and
    never turns into acceptance or into a block. An unanswered requirement is
    left out rather than assumed open, because a missing judgement is not a
    finding.
    """
    policy = thresholds() if policy is None else policy
    bar = policy["requirement_closed_min_noul"]
    gaps = []
    for index, text in enumerate(requirements or []):
        answer = (answers or {}).get(requirement_key(index))
        if isinstance(answer, dict) and isinstance(answer.get("noul"), (int, float)) \
                and not isinstance(answer["noul"], bool) and answer["noul"] < bar:
            gaps.append({"index": index + 1, "requirement": text,
                         "closed_noul": round(float(answer["noul"]), 4)})
    return gaps


def requirement_key(index):
    return "requirement_%02d" % (index + 1)


def _verdict(outcome, status=None, reason=None, threshold=None, checks_blocked=False):
    return {"outcome": outcome, "status": status, "reason": reason,
            "threshold": threshold, "checks_blocked": checks_blocked}


def report_summary(report):
    """The part of a checks report a decision actually reads."""
    if not report:
        return None
    return {"passed": report["passed"], "total": report["total"],
            "fresh": bool(report["fresh"]), "registered": bool(report["registered"])}


def review_summary(review):
    """The part of a review answer a decision actually reads."""
    if not review:
        return None
    action = review["next_action"]
    return {"action": action["choice"], "confidence": action["confidence"],
            "addresses_request": review["addresses_request"]["noul"]}


def decide_turn(attempt, readonly, changed, report, review, judge_state, policy=None):
    """Decide one worker attempt from recorded facts alone.

    ``report`` and ``review`` are the summaries above (or None), ``changed`` is
    the number of changed files, ``judge_state`` is one of JUDGE_STATES.
    Returns a verdict whose ``outcome`` is "return" (the turn ends with
    ``status``/``reason``) or "retry" (run another worker attempt).
    """
    if judge_state not in JUDGE_STATES:
        raise ValueError("judge_state must be one of " + ", ".join(JUDGE_STATES))
    policy = thresholds() if policy is None else policy
    last_attempt = attempt >= policy["max_attempts"]
    progress = bool(changed)

    if judge_state == "unavailable":
        # A missing judgement is not maximum confidence. The worker's result is
        # kept, but the turn cannot claim acceptance on an opinion never given.
        return _verdict("return", "needs_input", "judge_unavailable")

    action = review["action"] if review else "finish"
    confidence = review["confidence"] if review else None

    if report and report["total"] and (report["passed"] != report["total"] or not report["fresh"]):
        # An executed check that failed or went stale outranks any judgement.
        if last_attempt or not progress:
            return _verdict("return", "stopped", "checks_failed_or_no_progress", checks_blocked=True)
        return _verdict("retry", checks_blocked=True)

    confident_improve = (action == "improve" and confidence is not None
                         and confidence >= policy["improve_min_confidence"])
    if confident_improve and not readonly:
        if last_attempt or not progress:
            return _verdict("return", "stopped", "iteration_limit_or_no_progress",
                            threshold="improve_min_confidence")
        return _verdict("retry", threshold="improve_min_confidence")
    if action == "ask_user":
        return _verdict("return", "needs_input", "review_requests_clarification")
    # An "improve" below the bar is not a weak finding, it is the absence of one:
    # low confidence means the judge has no opinion, so it must not by itself send
    # the user away from a result that does answer them. Only weak correspondence
    # to the request does that. Measured case: improve at 0.26 confidence with
    # addresses_request 0.75 used to end a correct answered turn in needs_input.
    if bool(review) and review["addresses_request"] < policy["addresses_request_min_noul"]:
        return _verdict("return", "needs_input", "uncertain_request_correspondence",
                        threshold="addresses_request_min_noul")
    if report and report["registered"] and report["total"] and report["fresh"]:
        return _verdict("return", "accepted", "registered_checks_passed")
    return _verdict("return", "answered" if readonly else "ready",
                    "response_prepared_without_independent_acceptance")
