"""Turn policy as data and one pure function, so a decision can be replayed.

Every threshold that decides a turn lives here, not inline in the executor, and
every decision is a function of recorded inputs alone: no I/O, no clock, no
model call. A saved turn can therefore be re-decided from its journal, and a
threshold change can be measured against history before it is applied.

POLICY_VERSION must be raised whenever a threshold or a rule changes, because a
recorded decision is only comparable to a recomputed one under the same policy.
"""

POLICY_VERSION = 1

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
            raise ValueError("Неизвестный порог политики: " + str(name))
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("Порог %s должен быть числом." % name)
        if name == "max_attempts":
            if int(value) != value or value < 1:
                raise ValueError("max_attempts должен быть целым числом не меньше 1.")
            values[name] = int(value)
            continue
        if not 0.0 <= float(value) <= 1.0:
            raise ValueError("Порог %s должен лежать в диапазоне 0..1." % name)
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
        raise ValueError("judge_state должен быть одним из " + ", ".join(JUDGE_STATES))
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
    unaddressed = bool(review) and review["addresses_request"] < policy["addresses_request_min_noul"]
    unsure_improve = (action == "improve" and confidence is not None
                      and confidence < policy["improve_min_confidence"])
    if unaddressed or unsure_improve:
        return _verdict("return", "needs_input", "uncertain_request_correspondence",
                        threshold="addresses_request_min_noul" if unaddressed else "improve_min_confidence")
    if report and report["registered"] and report["total"] and report["fresh"]:
        return _verdict("return", "accepted", "registered_checks_passed")
    return _verdict("return", "answered" if readonly else "ready",
                    "response_prepared_without_independent_acceptance")
