"""Pure functions: how mastery is scored and how the next quiz is planned.

No database and no network in this file, so every rule can be tested alone.
"""

DECAY = 0.85           # an answer counts 85% as much as the next newer one
WINDOW = 20            # only the last 20 answers per topic are used
PRIOR_STRENGTH = 2.0   # the starting guess is worth about 2 answers
PRIOR_MASTERY = 0.5    # "unknown" topics start at 50%
MIN_PRIORITY = 0.1     # mastered topics still come back now and then

WEAK_BELOW = 0.45
STRONG_FROM = 0.75


def mastery_from_results(results_newest_first):
    """Score 0..1 from a list of right/wrong answers, newest first.

    Recent answers count more, and a starting guess of 50% stops a single
    lucky answer from looking like mastery.
    """
    weighted_correct = 0.0
    total_weight = 0.0
    for position, result in enumerate(list(results_newest_first)[:WINDOW]):
        weight = DECAY ** position
        weighted_correct += weight * (1 if result else 0)
        total_weight += weight
    prior = PRIOR_STRENGTH * PRIOR_MASTERY
    return (weighted_correct + prior) / (total_weight + PRIOR_STRENGTH)


def status_for(mastery, answered):
    if answered == 0:
        return "new"
    if mastery < WEAK_BELOW:
        return "weak"
    if mastery < STRONG_FROM:
        return "learning"
    return "strong"


def suggest_difficulty(mastery, answered):
    if answered == 0:
        return "medium"
    if mastery < WEAK_BELOW:
        return "easy"
    if mastery < STRONG_FROM:
        return "medium"
    return "hard"


def priority(mastery):
    """How much a topic needs practice: weak topics high, mastered ones low."""
    return max(MIN_PRIORITY, 1.0 - mastery)


def allocate_questions(priorities, total, max_topics=3):
    """Split `total` questions across the neediest topics.

    priorities: list of (topic_id, priority) in preferred tie-break order.
    Returns [(topic_id, n), ...] with n >= 1 and the n values adding up to
    `total` (when there is at least one topic).
    """
    if total <= 0 or not priorities:
        return []

    ranked = sorted(priorities, key=lambda item: -item[1])  # stable sort
    chosen = ranked[:min(max_topics, total, len(ranked))]
    weight_sum = sum(p for _, p in chosen)

    counts = {topic_id: 1 for topic_id, _ in chosen}
    remaining = total - len(chosen)
    if remaining > 0:
        shares = {t: remaining * p / weight_sum for t, p in chosen}
        for topic_id, share in shares.items():
            counts[topic_id] += int(share)
        leftover = total - sum(counts.values())
        by_remainder = sorted(
            chosen,
            key=lambda item: -(shares[item[0]] - int(shares[item[0]])),
        )
        for topic_id, _ in by_remainder[:leftover]:
            counts[topic_id] += 1

    order = {topic_id: i for i, (topic_id, _) in enumerate(chosen)}
    return sorted(counts.items(), key=lambda item: (-item[1], order[item[0]]))
