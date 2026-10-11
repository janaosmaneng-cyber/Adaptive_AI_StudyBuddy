"""Spaced repetition for flashcards (the SM-2 algorithm).

Pure functions again: give it a card's state and a rating, get the next state.
"""
from dataclasses import dataclass
from datetime import date, timedelta

# The four buttons shown under a flashcard, mapped to SM-2 quality (0-5).
QUALITY = {"again": 1, "hard": 3, "good": 4, "easy": 5}

START_EASE = 2.5
MIN_EASE = 1.3


@dataclass
class CardState:
    ease: float = START_EASE
    interval_days: int = 0
    repetitions: int = 0
    lapses: int = 0


def quality_from(rating):
    """Accept 'again'/'hard'/'good'/'easy' or a number 0-5."""
    if isinstance(rating, str):
        if rating not in QUALITY:
            raise ValueError(f"Unknown rating '{rating}'. Use one of {list(QUALITY)}.")
        return QUALITY[rating]
    if not 0 <= rating <= 5:
        raise ValueError("Quality must be between 0 and 5.")
    return int(rating)


def next_state(state, quality):
    """Return the card's new state after a review with this quality (0-5)."""
    if quality < 3:
        # Failed: start the card over. SM-2 leaves the ease factor unchanged.
        return CardState(
            ease=state.ease,
            interval_days=1,
            repetitions=0,
            lapses=state.lapses + (1 if state.repetitions > 0 else 0),
        )

    if state.repetitions == 0:
        interval = 1
    elif state.repetitions == 1:
        interval = 6
    else:
        interval = max(1, round(state.interval_days * state.ease))

    miss = 5 - quality
    ease = max(MIN_EASE, state.ease + (0.1 - miss * (0.08 + miss * 0.02)))
    return CardState(
        ease=round(ease, 4),
        interval_days=interval,
        repetitions=state.repetitions + 1,
        lapses=state.lapses,
    )


def due_date(today, interval_days):
    return today + timedelta(days=interval_days)
