# AdaptiveAI - student data layer (Phase 2, step 2)

Runs on the Streamlit side (your computer), not on Kaggle. It remembers what the
server forgets: answers, mastery per topic, and the flashcard review schedule.
Pure Python + SQLite, no GPU, no extra packages.

## Files

```text
student_data/
├── __init__.py   exports StudentStore and QUALITY
├── mastery.py    mastery score, status, difficulty, quiz allocation (pure functions)
├── srs.py        SM-2 spaced repetition (pure functions)
└── store.py      SQLite storage: StudentStore
tests/
└── test_student_data.py   33 tests
```

Run the tests from this folder: `python -m unittest discover -s tests -v`

## How mastery works

For each topic, the last 20 answers are used, newest first. Each older answer
counts 85% as much as the next newer one. A starting guess of 50% (worth about 2
answers) keeps one lucky answer from looking like mastery.

| Mastery | Status | Next-quiz difficulty |
|---|---|---|
| no answers yet | new | medium |
| below 0.45 | weak | easy |
| 0.45 to 0.75 | learning | medium |
| 0.75 or more | strong | hard |

The next quiz covers up to 3 topics, ranked by `priority = max(0.1, 1 - mastery)`.
Weak topics get the most questions, unseen topics come next, mastered topics last.
Every chosen topic gets at least one question.

## Flashcards

SM-2 scheduling. Buttons map to quality: again=1, hard=3, good=4, easy=5.
Good reviews give intervals of 1, 6, then about 15 days. "Again" restarts the card.
Questions answered wrong can be turned into flashcards automatically.

## How Streamlit uses it

```python
from student_data import StudentStore
student = StudentStore("student.db")

# 1. After /ingest (or GET /topics), save the topics
student.sync_topics(response["topics"])

# 2. Plan the next quiz, then ask the server for each part
plan = student.plan_adaptive_quiz(total=5)
quiz_id = student.start_quiz(plan=plan)
for item in plan:
    reply = post("/quiz", json={"n": item["n"], "topic_id": item["topic_id"],
                                "difficulty": item["difficulty"],
                                "avoid_questions": item["avoid_questions"]})
    # show reply["questions"], then for each answer:
    # student.record_answer(quiz_id, question, chosen_index)

# 3. After the quiz
student.quiz_summary(quiz_id)           # score, per-topic results
student.cards_from_mistakes(quiz_id)    # wrong answers -> flashcards

# 4. Flashcards
student.add_cards(post("/flashcards", json={"topic_id": tid})["flashcards"])
for card in student.due_cards():
    ...                                 # show it, then:
    student.review_card(card["id"], "good")   # again | hard | good | easy

# 5. Dashboard
student.topic_stats()         # mastery, status, cards due, per topic
student.quiz_history()        # score per quiz
student.mastery_timeline()    # mastery after each quiz, for the progress chart
```

## Notes

- One database file = one student. Use a different path per student.
- Topic ids come from the server and are stable for the same PDF, so progress
  survives a Kaggle restart as long as you upload the same PDF again.
- `reset_progress()` deletes answers, quizzes and flashcards but keeps topics.
