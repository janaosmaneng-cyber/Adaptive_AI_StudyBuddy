import os
import sys
import tempfile
import unittest
from datetime import date, datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from student_data import StudentStore
from student_data import mastery as M
from student_data import srs


class MasteryRules(unittest.TestCase):
    def test_unknown_topic_starts_at_fifty_percent(self):
        self.assertAlmostEqual(M.mastery_from_results([]), 0.5)

    def test_one_lucky_answer_is_not_mastery(self):
        self.assertAlmostEqual(M.mastery_from_results([1]), 2 / 3)
        self.assertEqual(M.status_for(M.mastery_from_results([1]), 1), "learning")

    def test_one_miss_is_weak(self):
        self.assertAlmostEqual(M.mastery_from_results([0]), 1 / 3)
        self.assertEqual(M.status_for(M.mastery_from_results([0]), 1), "weak")

    def test_three_right_in_a_row_is_strong(self):
        level = M.mastery_from_results([1, 1, 1])
        self.assertGreaterEqual(level, M.STRONG_FROM)
        self.assertEqual(M.status_for(level, 3), "strong")

    def test_recent_answers_count_more(self):
        improving = M.mastery_from_results([1, 1, 0, 0])   # newest first
        slipping = M.mastery_from_results([0, 0, 1, 1])
        self.assertGreater(improving, slipping)

    def test_only_last_window_answers_count(self):
        old_misses = [1] * M.WINDOW + [0] * 50
        self.assertAlmostEqual(M.mastery_from_results(old_misses),
                               M.mastery_from_results([1] * M.WINDOW))

    def test_difficulty_follows_mastery(self):
        self.assertEqual(M.suggest_difficulty(0.5, 0), "medium")
        self.assertEqual(M.suggest_difficulty(0.2, 4), "easy")
        self.assertEqual(M.suggest_difficulty(0.6, 4), "medium")
        self.assertEqual(M.suggest_difficulty(0.9, 4), "hard")

    def test_priority_has_a_floor(self):
        self.assertAlmostEqual(M.priority(0.2), 0.8)
        self.assertEqual(M.priority(0.99), M.MIN_PRIORITY)


class Allocation(unittest.TestCase):
    def test_counts_add_up_and_each_topic_gets_at_least_one(self):
        items = [("a", 0.8), ("b", 0.5), ("c", 0.3), ("d", 0.1)]
        for total in range(1, 11):
            plan = M.allocate_questions(items, total, max_topics=3)
            self.assertEqual(sum(n for _, n in plan), total)
            self.assertLessEqual(len(plan), 3)
            self.assertTrue(all(n >= 1 for _, n in plan))

    def test_weakest_topic_gets_the_most(self):
        plan = M.allocate_questions([("strong", 0.1), ("weak", 0.9), ("mid", 0.5)], 6)
        self.assertEqual(plan[0][0], "weak")
        self.assertGreater(plan[0][1], plan[-1][1])

    def test_fewer_questions_than_topics(self):
        plan = M.allocate_questions([("a", 0.9), ("b", 0.5), ("c", 0.2)], 2)
        self.assertEqual([t for t, _ in plan], ["a", "b"])

    def test_ties_keep_the_given_order(self):
        plan = M.allocate_questions([("x", 0.5), ("y", 0.5), ("z", 0.5), ("w", 0.5)], 3)
        self.assertEqual([t for t, _ in plan], ["x", "y", "z"])

    def test_empty_cases(self):
        self.assertEqual(M.allocate_questions([], 5), [])
        self.assertEqual(M.allocate_questions([("a", 0.5)], 0), [])


class SpacedRepetition(unittest.TestCase):
    def test_good_reviews_give_1_6_then_15_days(self):
        state = srs.CardState()
        intervals = []
        for _ in range(3):
            state = srs.next_state(state, srs.quality_from("good"))
            intervals.append(state.interval_days)
        self.assertEqual(intervals, [1, 6, 15])

    def test_ease_changes_by_quality(self):
        start = srs.CardState()
        self.assertAlmostEqual(srs.next_state(start, 4).ease, 2.5)
        self.assertAlmostEqual(srs.next_state(start, 5).ease, 2.6)
        self.assertAlmostEqual(srs.next_state(start, 3).ease, 2.36)

    def test_failing_resets_the_card_but_not_the_ease(self):
        state = srs.CardState(ease=2.3, interval_days=15, repetitions=3, lapses=0)
        after = srs.next_state(state, srs.quality_from("again"))
        self.assertEqual((after.interval_days, after.repetitions, after.lapses), (1, 0, 1))
        self.assertAlmostEqual(after.ease, 2.3)

    def test_failing_a_new_card_is_not_a_lapse(self):
        self.assertEqual(srs.next_state(srs.CardState(), 1).lapses, 0)

    def test_ease_never_drops_below_minimum(self):
        state = srs.CardState(ease=1.31, interval_days=6, repetitions=2)
        for _ in range(5):
            state = srs.next_state(state, 3)
        self.assertGreaterEqual(state.ease, srs.MIN_EASE)

    def test_bad_ratings_are_rejected(self):
        with self.assertRaises(ValueError):
            srs.quality_from("meh")
        with self.assertRaises(ValueError):
            srs.quality_from(9)


def make_topics():
    return [
        {"id": f"book.pdf#{i}", "doc": "book.pdf", "label": label,
         "pages": [i * 5 - 4, i * 5], "n_chunks": 10}
        for i, label in enumerate(["Cells", "Genetics", "Evolution", "Ecology"], start=1)
    ]


def make_question(topic_id, number, answer_index=0):
    return {"question": f"{topic_id} question {number}?", "options": ["A", "B", "C", "D"],
            "answer_index": answer_index, "topic_id": topic_id, "difficulty": "medium",
            "source_page": 1, "explanation": f"Because of {number}."}


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.dir.name, "student.db")
        self.store = StudentStore(self.path)
        self.store.sync_topics(make_topics())

    def tearDown(self):
        self.dir.cleanup()

    def answer(self, quiz_id, topic_id, number, right):
        question = make_question(topic_id, number)
        return self.store.record_answer(quiz_id, question, 0 if right else 1)

    def test_topics_are_saved_in_order_and_updated_not_duplicated(self):
        topics = make_topics()
        topics[0]["label"] = "Cell Biology"
        self.store.sync_topics(topics)
        stats = self.store.topic_stats()
        self.assertEqual([s["label"] for s in stats], ["Cell Biology", "Genetics", "Evolution", "Ecology"])

    def test_answers_are_graded_and_validated(self):
        quiz = self.store.start_quiz()
        self.assertTrue(self.store.record_answer(quiz, make_question("book.pdf#1", 1), 0))
        self.assertFalse(self.store.record_answer(quiz, make_question("book.pdf#1", 2), 3))
        with self.assertRaises(ValueError):
            self.store.record_answer(quiz, make_question("book.pdf#1", 3), 7)

    def test_first_quiz_covers_the_first_topics_evenly(self):
        plan = self.store.plan_adaptive_quiz(total=6)
        self.assertEqual([p["topic_id"] for p in plan], ["book.pdf#1", "book.pdf#2", "book.pdf#3"])
        self.assertEqual([p["n"] for p in plan], [2, 2, 2])
        self.assertTrue(all(p["difficulty"] == "medium" for p in plan))

    def test_adaptive_loop_targets_what_the_student_failed(self):
        """The demo: quiz 1 fails a topic, quiz 2 goes after it, then it improves."""
        quiz1 = self.store.start_quiz()
        self.answer(quiz1, "book.pdf#1", 1, True)
        self.answer(quiz1, "book.pdf#1", 2, True)
        self.answer(quiz1, "book.pdf#2", 1, False)
        self.answer(quiz1, "book.pdf#2", 2, False)
        self.answer(quiz1, "book.pdf#3", 1, True)
        self.answer(quiz1, "book.pdf#3", 2, False)

        plan = self.store.plan_adaptive_quiz(total=5)
        ids = [p["topic_id"] for p in plan]
        self.assertEqual(plan[0]["topic_id"], "book.pdf#2")          # the failed topic leads
        self.assertEqual(plan[0]["n"], 2)
        self.assertEqual(plan[0]["difficulty"], "easy")               # and gets easier questions
        self.assertNotIn("book.pdf#1", ids)                           # the mastered topic is skipped
        self.assertIn("book.pdf#4", ids)                              # the unseen topic is included
        self.assertEqual(sum(p["n"] for p in plan), 5)
        self.assertEqual(len(plan[0]["avoid_questions"]), 2)          # earlier questions not repeated

        before = self.store.mastery("book.pdf#2")
        quiz2 = self.store.start_quiz(plan=plan)
        self.answer(quiz2, "book.pdf#2", 3, True)
        self.answer(quiz2, "book.pdf#2", 4, True)
        self.assertGreater(self.store.mastery("book.pdf#2"), before)

        history = self.store.quiz_history()
        self.assertEqual([h["total"] for h in history], [6, 2])
        self.assertEqual(history[1]["score"], 100.0)

        timeline = [t for t in self.store.mastery_timeline() if t["topic_id"] == "book.pdf#2"]
        self.assertEqual([t["quiz_number"] for t in timeline], [1, 2])
        self.assertGreater(timeline[1]["mastery"], timeline[0]["mastery"])

    def test_stats_and_status(self):
        quiz = self.store.start_quiz()
        for n in (1, 2, 3):
            self.answer(quiz, "book.pdf#1", n, True)
        self.answer(quiz, "book.pdf#2", 1, False)
        stats = {s["topic_id"]: s for s in self.store.topic_stats()}
        self.assertEqual(stats["book.pdf#1"]["status"], "strong")
        self.assertEqual(stats["book.pdf#2"]["status"], "weak")
        self.assertEqual(stats["book.pdf#3"]["status"], "new")
        self.assertEqual(stats["book.pdf#1"]["accuracy"], 1.0)
        self.assertIsNone(stats["book.pdf#3"]["accuracy"])

    def test_quiz_summary_per_topic(self):
        quiz = self.store.start_quiz()
        self.answer(quiz, "book.pdf#1", 1, True)
        self.answer(quiz, "book.pdf#2", 1, False)
        summary = self.store.quiz_summary(quiz)
        self.assertEqual((summary["total"], summary["correct"], summary["score"]), (2, 1, 50.0))
        self.assertEqual([t["label"] for t in summary["by_topic"]], ["Cells", "Genetics"])
        with self.assertRaises(KeyError):
            self.store.quiz_summary(999)

    def test_mistakes_become_flashcards_once(self):
        quiz = self.store.start_quiz()
        self.answer(quiz, "book.pdf#1", 1, True)
        self.answer(quiz, "book.pdf#2", 1, False)
        self.answer(quiz, "book.pdf#2", 2, False)
        self.assertEqual(self.store.cards_from_mistakes(quiz), 2)
        self.assertEqual(self.store.cards_from_mistakes(quiz), 0)   # no duplicates
        card = self.store.due_cards()[0]
        self.assertEqual(card["topic_id"], "book.pdf#2")
        self.assertIn("A", card["back"])
        self.assertIn("Because of 1.", card["back"])

    def test_add_cards_skips_blanks_and_duplicates(self):
        cards = [{"front": "What is DNA?", "back": "A molecule.", "topic_id": "book.pdf#2"},
                 {"front": "what is dna?", "back": "again", "topic_id": "book.pdf#2"},
                 {"front": "", "back": "no front"}, {"front": "no back", "back": " "}]
        self.assertEqual(self.store.add_cards(cards), 1)
        self.assertEqual(self.store.card_counts()["total"], 1)

    def test_card_schedule_over_several_days(self):
        day1 = date(2026, 1, 1)
        self.store.add_cards([{"front": "Q", "back": "A", "topic_id": "book.pdf#1"}], today=day1)
        card_id = self.store.due_cards(today=day1)[0]["id"]
        self.assertEqual(self.store.card_counts(today=day1), {"total": 1, "due": 1, "new": 1})

        result = self.store.review_card(card_id, "good", today=day1)
        self.assertEqual((result["interval_days"], result["due_at"]), (1, "2026-01-02"))
        self.assertEqual(self.store.due_cards(today=day1), [])
        self.assertEqual(len(self.store.due_cards(today=date(2026, 1, 2))), 1)

        result = self.store.review_card(card_id, "good", today=date(2026, 1, 2))
        self.assertEqual((result["interval_days"], result["due_at"]), (6, "2026-01-08"))

        result = self.store.review_card(card_id, "again", today=date(2026, 1, 8))
        self.assertEqual((result["interval_days"], result["repetitions"], result["lapses"]), (1, 0, 1))
        self.assertEqual(result["due_at"], "2026-01-09")
        self.assertEqual(self.store.card_counts(today=date(2026, 1, 8))["new"], 0)

        with self.assertRaises(KeyError):
            self.store.review_card(999, "good")

    def test_due_cards_can_filter_by_topic_and_shows_in_stats(self):
        today = date(2026, 3, 1)
        self.store.add_cards([{"front": "a", "back": "x", "topic_id": "book.pdf#1"},
                              {"front": "b", "back": "y", "topic_id": "book.pdf#2"}], today=today)
        self.assertEqual(len(self.store.due_cards(topic_id="book.pdf#2", today=today)), 1)
        stats = {s["topic_id"]: s for s in self.store.topic_stats(today=today)}
        self.assertEqual((stats["book.pdf#1"]["cards_total"], stats["book.pdf#1"]["cards_due"]), (1, 1))

    def test_data_survives_reopening_the_database(self):
        quiz = self.store.start_quiz()
        self.answer(quiz, "book.pdf#2", 1, False)
        self.store.add_cards([{"front": "q", "back": "a", "topic_id": "book.pdf#2"}])
        reopened = StudentStore(self.path)
        self.assertEqual(reopened.topic_stats()[1]["answered"], 1)
        self.assertEqual(reopened.card_counts()["total"], 1)

    def test_reset_progress_keeps_topics(self):
        quiz = self.store.start_quiz()
        self.answer(quiz, "book.pdf#1", 1, True)
        self.store.add_cards([{"front": "q", "back": "a"}])
        self.store.reset_progress()
        self.assertEqual(self.store.quiz_history(), [])
        self.assertEqual(self.store.card_counts()["total"], 0)
        self.assertEqual(len(self.store.topic_stats()), 4)

    def test_arabic_text_round_trips(self):
        quiz = self.store.start_quiz()
        question = make_question("book.pdf#1", 1)
        question["question"] = "ما هي عاصمة مصر؟"
        question["options"] = ["القاهرة", "الإسكندرية", "الجيزة", "أسوان"]
        self.store.record_answer(quiz, question, 1)
        self.assertEqual(self.store.recent_questions("book.pdf#1"), ["ما هي عاصمة مصر؟"])
        self.assertEqual(self.store.cards_from_mistakes(quiz), 1)
        self.assertIn("القاهرة", self.store.due_cards()[0]["back"])

    def test_empty_database_is_safe(self):
        empty = StudentStore(os.path.join(self.dir.name, "empty.db"))
        self.assertEqual(empty.plan_adaptive_quiz(), [])
        self.assertEqual(empty.topic_stats(), [])
        self.assertEqual(empty.mastery_timeline(), [])
        self.assertEqual(empty.due_cards(), [])


if __name__ == "__main__":
    unittest.main()
