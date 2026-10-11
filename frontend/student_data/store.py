"""SQLite storage for one student: answers, mastery, quizzes and flashcards.

Everything the server forgets (it is stateless) lives here, on the Streamlit side.
Dates are injectable (`now`, `today`) so behaviour over days can be tested.
"""
import json
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timezone

from . import mastery as M
from . import srs

SCHEMA = """
CREATE TABLE IF NOT EXISTS topics (
    topic_id TEXT PRIMARY KEY,
    doc TEXT NOT NULL DEFAULT '',
    label TEXT NOT NULL DEFAULT '',
    page_from INTEGER,
    page_to INTEGER,
    n_chunks INTEGER NOT NULL DEFAULT 0,
    position INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS quizzes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    kind TEXT NOT NULL DEFAULT 'adaptive',
    plan TEXT
);
CREATE TABLE IF NOT EXISTS answers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    quiz_id INTEGER NOT NULL REFERENCES quizzes(id),
    answered_at TEXT NOT NULL,
    topic_id TEXT NOT NULL DEFAULT '',
    question TEXT NOT NULL,
    options TEXT NOT NULL,
    answer_index INTEGER NOT NULL,
    chosen_index INTEGER NOT NULL,
    correct INTEGER NOT NULL,
    difficulty TEXT,
    source_page INTEGER,
    explanation TEXT
);
CREATE INDEX IF NOT EXISTS idx_answers_topic ON answers(topic_id, id);
CREATE TABLE IF NOT EXISTS cards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    topic_id TEXT NOT NULL DEFAULT '',
    front TEXT NOT NULL,
    front_key TEXT NOT NULL,
    back TEXT NOT NULL,
    source_page INTEGER,
    created_at TEXT NOT NULL,
    ease REAL NOT NULL,
    interval_days INTEGER NOT NULL DEFAULT 0,
    repetitions INTEGER NOT NULL DEFAULT 0,
    lapses INTEGER NOT NULL DEFAULT 0,
    due_at TEXT NOT NULL,
    last_reviewed TEXT,
    UNIQUE(topic_id, front_key)
);
CREATE TABLE IF NOT EXISTS reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    card_id INTEGER NOT NULL REFERENCES cards(id),
    reviewed_at TEXT NOT NULL,
    quality INTEGER NOT NULL
);
"""


class StudentStore:
    def __init__(self, path="student.db"):
        self.path = path
        with self._db() as db:
            db.executescript(SCHEMA)

    # ---------------------------------------------------------------- helpers
    @contextmanager
    def _db(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    @staticmethod
    def _stamp(now):
        return (now or datetime.now(timezone.utc)).isoformat(timespec="seconds")

    @staticmethod
    def _today(today):
        return today or date.today()

    # ----------------------------------------------------------------- topics
    def sync_topics(self, topics):
        """Save the topics returned by the server's /ingest or GET /topics."""
        with self._db() as db:
            row = db.execute("SELECT COALESCE(MAX(position), -1) AS p FROM topics").fetchone()
            next_position = row["p"] + 1
            for topic in topics:
                pages = topic.get("pages") or [None, None]
                exists = db.execute(
                    "SELECT 1 FROM topics WHERE topic_id=?", (topic["id"],)
                ).fetchone()
                if exists:
                    db.execute(
                        "UPDATE topics SET doc=?, label=?, page_from=?, page_to=?, n_chunks=? "
                        "WHERE topic_id=?",
                        (topic.get("doc", ""), topic.get("label", ""), pages[0], pages[1],
                         topic.get("n_chunks", 0), topic["id"]),
                    )
                else:
                    db.execute(
                        "INSERT INTO topics (topic_id, doc, label, page_from, page_to, n_chunks, position) "
                        "VALUES (?,?,?,?,?,?,?)",
                        (topic["id"], topic.get("doc", ""), topic.get("label", ""),
                         pages[0], pages[1], topic.get("n_chunks", 0), next_position),
                    )
                    next_position += 1

    # ---------------------------------------------------------------- quizzes
    def start_quiz(self, kind="adaptive", plan=None, now=None):
        with self._db() as db:
            cursor = db.execute(
                "INSERT INTO quizzes (started_at, kind, plan) VALUES (?,?,?)",
                (self._stamp(now), kind, json.dumps(plan, ensure_ascii=False) if plan else None),
            )
            return cursor.lastrowid

    def record_answer(self, quiz_id, question, chosen_index, now=None):
        """Save one answer. `question` is one item from the server's /quiz reply."""
        options = question["options"]
        if not 0 <= chosen_index < len(options):
            raise ValueError("chosen_index is outside the question's options.")
        correct = int(chosen_index == question["answer_index"])
        with self._db() as db:
            db.execute(
                "INSERT INTO answers (quiz_id, answered_at, topic_id, question, options, "
                "answer_index, chosen_index, correct, difficulty, source_page, explanation) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (quiz_id, self._stamp(now), question.get("topic_id") or "",
                 question["question"], json.dumps(options, ensure_ascii=False),
                 question["answer_index"], chosen_index, correct,
                 question.get("difficulty"), question.get("source_page"),
                 question.get("explanation")),
            )
        return bool(correct)

    def quiz_summary(self, quiz_id):
        with self._db() as db:
            quiz = db.execute("SELECT * FROM quizzes WHERE id=?", (quiz_id,)).fetchone()
            if quiz is None:
                raise KeyError(f"No quiz with id {quiz_id}")
            rows = db.execute(
                "SELECT a.topic_id, COUNT(*) AS total, SUM(a.correct) AS correct, "
                "COALESCE(t.label, a.topic_id) AS label "
                "FROM answers a LEFT JOIN topics t ON t.topic_id = a.topic_id "
                "WHERE a.quiz_id=? GROUP BY a.topic_id ORDER BY MIN(a.id)",
                (quiz_id,),
            ).fetchall()
        by_topic = [
            {"topic_id": r["topic_id"], "label": r["label"] or "Unassigned",
             "total": r["total"], "correct": r["correct"]}
            for r in rows
        ]
        total = sum(t["total"] for t in by_topic)
        correct = sum(t["correct"] for t in by_topic)
        return {
            "quiz_id": quiz_id, "started_at": quiz["started_at"], "kind": quiz["kind"],
            "total": total, "correct": correct,
            "score": round(100 * correct / total, 1) if total else None,
            "by_topic": by_topic,
        }

    def quiz_history(self):
        with self._db() as db:
            ids = [r["id"] for r in db.execute(
                "SELECT DISTINCT q.id FROM quizzes q JOIN answers a ON a.quiz_id = q.id ORDER BY q.id")]
        return [self.quiz_summary(i) for i in ids]

    def recent_questions(self, topic_id, limit=20):
        """Question texts already asked for a topic, to pass as `avoid_questions`."""
        with self._db() as db:
            rows = db.execute(
                "SELECT question FROM answers WHERE topic_id=? ORDER BY id DESC LIMIT ?",
                (topic_id, limit),
            ).fetchall()
        return [r["question"] for r in rows]

    # ---------------------------------------------------------------- mastery
    def _results(self, db, topic_id):
        rows = db.execute(
            "SELECT correct FROM answers WHERE topic_id=? ORDER BY id DESC LIMIT ?",
            (topic_id, M.WINDOW),
        ).fetchall()
        return [r["correct"] for r in rows]

    def mastery(self, topic_id):
        with self._db() as db:
            return M.mastery_from_results(self._results(db, topic_id))

    def topic_stats(self, doc=None, today=None):
        today_text = self._today(today).isoformat()
        with self._db() as db:
            query = "SELECT * FROM topics"
            params = ()
            if doc:
                query += " WHERE doc=?"
                params = (doc,)
            topics = db.execute(query + " ORDER BY position", params).fetchall()
            stats = []
            for t in topics:
                results = self._results(db, t["topic_id"])
                total_answers = db.execute(
                    "SELECT COUNT(*) AS n, COALESCE(SUM(correct),0) AS c FROM answers WHERE topic_id=?",
                    (t["topic_id"],),
                ).fetchone()
                cards = db.execute(
                    "SELECT COUNT(*) AS total, "
                    "COALESCE(SUM(CASE WHEN due_at <= ? THEN 1 ELSE 0 END),0) AS due "
                    "FROM cards WHERE topic_id=?",
                    (today_text, t["topic_id"]),
                ).fetchone()
                level = M.mastery_from_results(results)
                answered = total_answers["n"]
                stats.append({
                    "topic_id": t["topic_id"], "doc": t["doc"], "label": t["label"],
                    "pages": [t["page_from"], t["page_to"]],
                    "answered": answered, "correct": total_answers["c"],
                    "accuracy": round(total_answers["c"] / answered, 3) if answered else None,
                    "mastery": round(level, 3),
                    "status": M.status_for(level, answered),
                    "cards_total": cards["total"], "cards_due": cards["due"],
                })
        return stats

    def plan_adaptive_quiz(self, total=5, max_topics=3, doc=None):
        """Decide which topics the next quiz covers, how many questions each,
        at what difficulty, and which questions not to repeat.

        Returns a list of dicts. For each one, call the server's POST /quiz with
        topic_id, n, difficulty and avoid_questions.
        """
        stats = self.topic_stats(doc=doc)
        if not stats:
            return []
        by_id = {s["topic_id"]: s for s in stats}
        # Among equal priorities, topics the student has answered least come first.
        ordered = sorted(stats, key=lambda s: s["answered"])
        items = [(s["topic_id"], M.priority(s["mastery"])) for s in ordered]

        plan = []
        for topic_id, n in M.allocate_questions(items, total, max_topics):
            s = by_id[topic_id]
            plan.append({
                "topic_id": topic_id, "label": s["label"], "n": n,
                "difficulty": M.suggest_difficulty(s["mastery"], s["answered"]),
                "mastery": s["mastery"], "status": s["status"],
                "avoid_questions": self.recent_questions(topic_id),
            })
        return plan

    def mastery_timeline(self):
        """Mastery per topic after each quiz, for the progress chart."""
        with self._db() as db:
            labels = {r["topic_id"]: r["label"] for r in db.execute("SELECT topic_id, label FROM topics")}
            rows = db.execute(
                "SELECT quiz_id, topic_id, correct FROM answers WHERE topic_id != '' ORDER BY id"
            ).fetchall()
        quiz_ids = []
        for r in rows:
            if r["quiz_id"] not in quiz_ids:
                quiz_ids.append(r["quiz_id"])

        timeline = []
        for number, quiz_id in enumerate(quiz_ids, start=1):
            history = {}
            for r in rows:
                if r["quiz_id"] <= quiz_id:
                    history.setdefault(r["topic_id"], []).append(r["correct"])
            for topic_id, results in history.items():
                timeline.append({
                    "quiz_number": number, "quiz_id": quiz_id, "topic_id": topic_id,
                    "label": labels.get(topic_id, topic_id),
                    "mastery": round(M.mastery_from_results(list(reversed(results))[:M.WINDOW]), 3),
                })
        return timeline

    # ------------------------------------------------------------- flashcards
    def add_cards(self, cards, today=None):
        """Save flashcards from the server's /flashcards reply. Returns how many were new."""
        today = self._today(today)
        added = 0
        with self._db() as db:
            for card in cards:
                front = (card.get("front") or "").strip()
                back = (card.get("back") or "").strip()
                if not front or not back:
                    continue
                cursor = db.execute(
                    "INSERT OR IGNORE INTO cards (topic_id, front, front_key, back, source_page, "
                    "created_at, ease, interval_days, repetitions, lapses, due_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (card.get("topic_id") or "", front, front.casefold(), back,
                     card.get("source_page"), today.isoformat(), srs.START_EASE, 0, 0, 0,
                     today.isoformat()),
                )
                added += cursor.rowcount
        return added

    def cards_from_mistakes(self, quiz_id, today=None):
        """Turn the questions a student got wrong in a quiz into flashcards."""
        with self._db() as db:
            wrong = db.execute(
                "SELECT * FROM answers WHERE quiz_id=? AND correct=0 ORDER BY id", (quiz_id,)
            ).fetchall()
        cards = []
        for a in wrong:
            options = json.loads(a["options"])
            back = options[a["answer_index"]]
            if a["explanation"]:
                back += "\n\n" + a["explanation"]
            cards.append({"front": a["question"], "back": back,
                          "topic_id": a["topic_id"], "source_page": a["source_page"]})
        return self.add_cards(cards, today=today)

    def due_cards(self, limit=20, topic_id=None, today=None):
        query = "SELECT * FROM cards WHERE due_at <= ?"
        params = [self._today(today).isoformat()]
        if topic_id:
            query += " AND topic_id=?"
            params.append(topic_id)
        query += " ORDER BY due_at, id LIMIT ?"
        params.append(limit)
        with self._db() as db:
            return [dict(r) for r in db.execute(query, params).fetchall()]

    def review_card(self, card_id, rating, today=None, now=None):
        """Apply a review. rating: 'again' | 'hard' | 'good' | 'easy' (or 0-5)."""
        quality = srs.quality_from(rating)
        today = self._today(today)
        with self._db() as db:
            card = db.execute("SELECT * FROM cards WHERE id=?", (card_id,)).fetchone()
            if card is None:
                raise KeyError(f"No card with id {card_id}")
            new = srs.next_state(
                srs.CardState(card["ease"], card["interval_days"], card["repetitions"], card["lapses"]),
                quality,
            )
            due = srs.due_date(today, new.interval_days)
            db.execute(
                "UPDATE cards SET ease=?, interval_days=?, repetitions=?, lapses=?, "
                "due_at=?, last_reviewed=? WHERE id=?",
                (new.ease, new.interval_days, new.repetitions, new.lapses,
                 due.isoformat(), today.isoformat(), card_id),
            )
            db.execute(
                "INSERT INTO reviews (card_id, reviewed_at, quality) VALUES (?,?,?)",
                (card_id, self._stamp(now), quality),
            )
        return {"card_id": card_id, "interval_days": new.interval_days,
                "due_at": due.isoformat(), "ease": new.ease,
                "repetitions": new.repetitions, "lapses": new.lapses}

    def card_counts(self, today=None):
        with self._db() as db:
            row = db.execute(
                "SELECT COUNT(*) AS total, "
                "COALESCE(SUM(CASE WHEN due_at <= ? THEN 1 ELSE 0 END),0) AS due, "
                "COALESCE(SUM(CASE WHEN last_reviewed IS NULL THEN 1 ELSE 0 END),0) AS new "
                "FROM cards",
                (self._today(today).isoformat(),),
            ).fetchone()
        return {"total": row["total"], "due": row["due"], "new": row["new"]}

    # ------------------------------------------------------------------ reset
    def reset_progress(self):
        """Delete answers, quizzes and flashcards. Topics are kept."""
        with self._db() as db:
            for table in ("reviews", "cards", "answers", "quizzes"):
                db.execute(f"DELETE FROM {table}")
