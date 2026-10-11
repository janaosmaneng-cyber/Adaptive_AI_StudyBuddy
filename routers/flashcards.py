import random

from fastapi import APIRouter, Depends, HTTPException
from auth import check_api_key
from schemas import FlashcardRequest, Flashcard
from services.json_utils import get_json_array
from services.model_service import generate_text
from services.topic_service import tag_item_topic
from services.vector_store import store, format_context

router = APIRouter()
MAX_ATTEMPTS = 3


def validate_card(item):
    """Return a valid flashcard or skip malformed model output."""
    if not isinstance(item, dict):
        return None
    try:
        card = Flashcard(
            front=str(item.get("front", "")).strip(),
            back=str(item.get("back", "")).strip(),
            source_page=item.get("source_page"),
        )
        if card.source_page is not None and card.source_page < 1:
            return None
        return card.model_dump()
    except Exception:
        return None


def make_prompt(context, count, topic, previous):
    topic_instruction = f"Focus on the topic '{topic}'." if topic else "Cover the supplied material."
    avoid_instruction = ""
    if previous:
        avoid_instruction = "\nDo not repeat these card fronts:\n- " + "\n- ".join(previous)

    return f"""
{topic_instruction}
Create {count} concise study flashcards, one idea per card.
Use only the context below. Return ONLY a valid JSON array.
Each object must have:
- front: a short question or term
- back: the answer in 1-3 sentences
- source_page: a page number shown in the context
Do not invent facts or page numbers.
{avoid_instruction}

Context:
{context}
"""


@router.post("/flashcards", dependencies=[Depends(check_api_key)])
def create_flashcards(request: FlashcardRequest):
    if not store.chunks:
        raise HTTPException(status_code=400, detail="No PDF material indexed yet. Call /ingest first.")

    if request.topic_id:
        chunks = store.chunks_for_topic(request.topic_id)
        if not chunks:
            raise HTTPException(status_code=404, detail="Unknown topic_id. Call /topics.")
        chunks = sorted(random.sample(chunks, min(5, len(chunks))), key=lambda chunk: chunk["page"])
        topic = store.topics[request.topic_id]["label"]
    else:
        chunks = store.random_chunks(5)
        topic = None

    if not chunks:
        raise HTTPException(status_code=400, detail="No relevant material found.")

    context = format_context(chunks)
    cards = []
    seen = {front.strip().casefold() for front in request.avoid_fronts}
    attempts = 0

    while len(cards) < request.n and attempts < MAX_ATTEMPTS:
        attempts += 1
        needed = request.n - len(cards)
        prompt = make_prompt(
            context, needed, topic,
            request.avoid_fronts[:20] + [card["front"] for card in cards],
        )
        output = generate_text(
            [
                {"role": "system", "content": "Create concise study flashcards. Return valid JSON only."},
                {"role": "user", "content": prompt},
            ],
            max_new_tokens=min(2000, 150 * needed),
            temperature=0.4,
        )

        for item in get_json_array(output):
            card = validate_card(item)
            if not card:
                continue
            key = card["front"].strip().casefold()
            if key in seen:
                continue
            seen.add(key)
            tag_item_topic(card, chunks, request.topic_id)
            cards.append(card)
            if len(cards) == request.n:
                break

    if not cards:
        raise HTTPException(
            status_code=502,
            detail="The model did not return valid flashcards after 3 attempts. Try again.",
        )

    return {
        "flashcards": cards[:request.n],
        "requested_count": request.n,
        "returned_count": min(len(cards), request.n),
        "attempts": attempts,
        "note": None if len(cards) >= request.n else "Fewer valid flashcards were returned than requested.",
    }
