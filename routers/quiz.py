import random

from fastapi import APIRouter, Depends, HTTPException
from auth import check_api_key
from schemas import QuizRequest, QuizQuestion
from services.json_utils import get_json_array
from services.model_service import generate_text
from services.topic_service import tag_item_topic
from services.vector_store import store, format_context

router = APIRouter()
MAX_ATTEMPTS = 3


def validate_question(item, difficulty):
    """Keep only questions with the expected multiple-choice structure."""
    if not isinstance(item, dict):
        return None

    item.setdefault("difficulty", difficulty)
    item.setdefault("topic", "General")
    item.setdefault("explanation", "")

    try:
        question = QuizQuestion(**item)
        if len(question.options) != 4 or any(not option.strip() for option in question.options):
            return None
        if question.source_page is not None and question.source_page < 1:
            return None
        return question.model_dump()
    except Exception:
        return None


def make_prompt(context, count, topic, difficulty, previous):
    topic_instruction = f"Focus on the topic '{topic}'." if topic else "Cover the supplied material."
    avoid_instruction = ""
    if previous:
        avoid_instruction = "\nDo not repeat these questions:\n- " + "\n- ".join(previous)

    return f"""
{topic_instruction}
Create {count} multiple-choice questions at {difficulty} difficulty.
Use only the context below. Return ONLY a JSON array.
Each object must have: question, options (exactly 4 strings), answer_index (0-3),
topic, difficulty, explanation, and source_page (a page number shown in the context).
Make the correct answer unambiguous. Do not invent facts or page numbers.
{avoid_instruction}

Context:
{context}
"""


@router.post("/quiz", dependencies=[Depends(check_api_key)])
def create_quiz(request: QuizRequest):
    if not store.chunks:
        raise HTTPException(status_code=400, detail="No PDF material indexed yet. Call /ingest first.")

    # Pick context from the selected topic, a text search, or the full collection.
    if request.topic_id:
        chunks = store.chunks_for_topic(request.topic_id)
        if not chunks:
            raise HTTPException(status_code=404, detail="Unknown topic_id. Call /topics.")
        chunks = sorted(random.sample(chunks, min(5, len(chunks))), key=lambda chunk: chunk["page"])
        topic = store.topics[request.topic_id]["label"]
    elif request.topic:
        chunks = store.search(request.topic, 5)
        topic = request.topic
    else:
        chunks = store.random_chunks(5)
        topic = None

    if not chunks:
        raise HTTPException(status_code=400, detail="No relevant material found.")

    context = format_context(chunks)
    questions = []
    seen = {text.strip().casefold() for text in request.avoid_questions}
    attempts = 0

    while len(questions) < request.n and attempts < MAX_ATTEMPTS:
        attempts += 1
        needed = request.n - len(questions)
        prompt = make_prompt(
            context, needed, topic, request.difficulty,
            request.avoid_questions[:20] + [q["question"] for q in questions],
        )
        output = generate_text(
            [
                {"role": "system", "content": "Create accurate quizzes. Return valid JSON only."},
                {"role": "user", "content": prompt},
            ],
            max_new_tokens=min(2500, 350 * needed),
            temperature=0.4,
        )

        for item in get_json_array(output):
            question = validate_question(item, request.difficulty)
            if not question:
                continue
            key = question["question"].strip().casefold()
            if key in seen:
                continue
            seen.add(key)
            # Always attach a stable topic ID, including when no topic was selected.
            tag_item_topic(question, chunks, request.topic_id)
            questions.append(question)
            if len(questions) == request.n:
                break

    if not questions:
        raise HTTPException(
            status_code=502,
            detail="The model did not return valid quiz questions after 3 attempts. Try again.",
        )

    return {
        "questions": questions[:request.n],
        "requested_count": request.n,
        "returned_count": min(len(questions), request.n),
        "attempts": attempts,
        "note": None if len(questions) >= request.n else "Fewer valid questions were returned than requested.",
    }
