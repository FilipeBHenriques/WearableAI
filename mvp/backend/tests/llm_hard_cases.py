"""Hard-but-possible cases run against the REAL Ollama + sentence-transformer
models (nothing mocked) to see how the current model choice actually performs
on ambiguous, adversarial, or multi-part input.

These are deliberately harder than the mocked unit tests elsewhere in this
directory. They are not a correctness gate — a failure here means "the model
got this particular hard case wrong today," not "the code is broken." Treat
red as a prompt/model-quality signal to investigate, not a regression to fix
blindly.

Named without a `test_` prefix on purpose — it is NOT picked up by
`python -m unittest discover -s tests -p "test_*.py"`, so a hard case going
red doesn't flip the regular (mocked, fast, deterministic) suite red too.

Run explicitly: `python -m unittest tests.llm_hard_cases -v`

Skipped automatically when Ollama isn't reachable (e.g. in CI).
"""

import tempfile
import unittest
from pathlib import Path

import database
from services import location_service, model_service, note_pipeline, note_service, relationship_service


def _llm_available() -> bool:
    return model_service.get_llm_config_status()["configured"]


@unittest.skipUnless(_llm_available(), "requires a running, configured Ollama instance")
class HardCaseLLMTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        database.DB_PATH = Path(self.temp_dir.name) / "test.db"
        database.init_db()

    def tearDown(self):
        self.temp_dir.cleanup()

    def _capture(self, text: str):
        return note_pipeline.process_text(text)

    def test_deadline_duration_recurrence_and_location_all_in_one_note(self):
        """Everything the consolidated prompt can extract, packed into one note."""
        location_service.save_current_location("office", 40.1, -8.2)

        result = self._capture(
            "meet the trainer at the office every Tuesday and Thursday at 7am for 45 minutes"
        )

        print("\n[hard: all-in-one]", result.repeat_cycle, result.repeat_days, result.repeat_time, result.estimated_duration_minutes, result.location_name)
        self.assertEqual(result.repeat_cycle, "weekly")
        self.assertEqual(sorted(result.repeat_days or []), [2, 4])
        self.assertEqual(result.repeat_time, "07:00")
        self.assertEqual(result.estimated_duration_minutes, 45)
        self.assertEqual(result.location_name, "office")

    def test_negated_deadline_is_not_treated_as_urgent(self):
        """'by tomorrow' appears, but negated — a naive keyword match would set a deadline anyway."""
        result = self._capture("I don't need to finish this by tomorrow, there's no rush at all")

        print("\n[hard: negated deadline]", result.deadline_at, result.urgency_reason)
        self.assertIsNone(result.deadline_at)

    def test_decoy_numbers_are_not_mistaken_for_duration(self):
        """Numbers that look like a duration/time hint but describe something else entirely."""
        result = self._capture("call flight AA1234 landing at gate 45 tomorrow morning")

        print("\n[hard: decoy numbers]", result.deadline_at, result.estimated_duration_minutes)
        self.assertIsNone(result.estimated_duration_minutes)

    def test_one_time_deadline_is_not_mistaken_for_recurrence(self):
        """'every' appears but describes a one-time completed action, not a repeating schedule."""
        result = self._capture("I checked every single box on the form before submitting it yesterday")

        print("\n[hard: fake recurrence]", result.repeat_cycle, result.is_repeating)
        self.assertIsNone(result.repeat_cycle)

    def test_conflicting_dates_still_resolves_to_the_corrected_one(self):
        """Two dates in one sentence, the second explicitly overriding the first."""
        result = self._capture("let's meet tomorrow — actually scratch that, let's do next Friday instead")

        print("\n[hard: conflicting dates]", result.deadline_at)
        self.assertIsNotNone(result.deadline_at)

    def test_ambiguous_relationship_links_to_the_right_topic_not_the_wrong_one(self):
        """Two unrelated existing notes plus a third note that's a genuine (not
        trivial-embedding) paraphrase of one of them — real embeddings decide
        whether this lands in the ambiguous band at all, and if it does, whether
        the LLM tie-break picks the right parent."""
        birthday_id, _ = note_service.save("plan Sarah's surprise birthday party for next month")
        unrelated_id, _ = note_service.save("renew the car insurance before it lapses")

        result = self._capture("need to book the venue and order the cake for the party")

        print("\n[hard: relationship] saved=", result.saved, "command_type=", result.command_type)
        self.assertTrue(result.saved, f"note was not saved as take_note (got command_type={result.command_type!r})")

        linked = note_service.get_by_id(result.id)
        print("[hard: relationship] parent_note_id=", linked.parent_note_id, "expected birthday_id=", birthday_id, "not unrelated_id=", unrelated_id)
        if linked.parent_note_id is not None:
            self.assertEqual(linked.parent_note_id, birthday_id)

    def test_location_choice_among_two_similar_saved_locations(self):
        """Two saved locations that both plausibly match 'the gym' — genuinely
        ambiguous, not a trick; documents which way the model leans."""
        home_gym = location_service.save_current_location("home gym", 40.10, -8.20)
        planet_fitness = location_service.save_current_location("planet fitness", 40.15, -8.25)

        result = self._capture("stretch at the gym after work")

        print("\n[hard: similar locations]", result.location_name, "options were:", home_gym.name, "/", planet_fitness.name)
        self.assertIn(result.location_id, (home_gym.id, planet_fitness.id, None))

    def test_command_classification_does_not_misfire_on_metaphor(self):
        """'this feels like my second home' names a place metaphorically, not
        literally — save_location should require an actual GPS-worthy place name."""
        result = self._capture("this coffee shop feels like my second home honestly")

        print("\n[hard: metaphor command]", result.command_type, result.location_name)
        self.assertEqual(result.command_type, "take_note")

    def test_long_rambling_note_still_finds_the_buried_deadline(self):
        """Deadline signal buried in the middle of an otherwise unrelated ramble."""
        result = self._capture(
            "so I was thinking about repainting the kitchen, maybe a light green, "
            "and also I keep forgetting but I really need to submit the tax forms "
            "before end of week, anyway the green might be too bright for the room"
        )

        print("\n[hard: buried deadline]", result.deadline_at, result.urgency_reason)
        self.assertIsNotNone(result.deadline_at)


def _print_tree(root_id: int | None, by_parent: dict, notes_by_id: dict, depth: int = 0) -> None:
    for child_id in by_parent.get(root_id, []):
        note = notes_by_id[child_id]
        print("  " * depth + f"- [{child_id}] {note.text}")
        _print_tree(child_id, by_parent, notes_by_id, depth + 1)


@unittest.skipUnless(_llm_available(), "requires a running, configured Ollama instance")
class ProjectDevelopmentScenarioTests(unittest.TestCase):
    """Real-life scenario: someone brainstorming a game project out loud over a
    long session, several threads interleaved (character mechanics, save
    system, level design) plus unrelated life notes mixed in, and a late note
    that should link back into an earlier thread despite unrelated notes in
    between. Exercises real embeddings + the LLM tie-break at depth, not just
    a single parent/child pair — this is where relationship_service's
    exclude-my-own-descendants logic (_candidate_notes) and multi-hop nesting
    actually get stressed."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        database.DB_PATH = Path(self.temp_dir.name) / "test.db"
        database.init_db()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_interleaved_dev_session_builds_sensible_nested_threads(self):
        notes_in_order = [
            "starting a new 2D platformer game project called Pixel Quest",
            "need to design the main character sprite sheet for Pixel Quest",
            "the character should have a double jump ability",
            "also want a dash move for the character, short cooldown",
            "let's add a save system using JSON files",
            "the save system should store player position and inventory",
            "design the first level, a forest area with platforming challenges",
            "the forest level needs moving platforms and spikes",
            "remember to buy more coffee filters",
            "add a boss fight at the end of the forest level",
            "the boss should have three phases with increasing difficulty",
            "fix the bug where double jump doesn't reset properly after landing",
        ]

        ids = []
        for text in notes_in_order:
            result = note_pipeline.process_text(text)
            self.assertTrue(result.saved, f"expected a note, got command_type={result.command_type!r} for: {text!r}")
            ids.append(result.id)

        coffee_id = ids[8]
        double_jump_id = ids[2]
        bugfix_id = ids[11]

        all_notes = note_service.get_all_flat()
        notes_by_id = {note.id: note for note in all_notes}
        by_parent: dict[int | None, list[int]] = {}
        for note in all_notes:
            by_parent.setdefault(note.parent_note_id, []).append(note.id)

        print("\n[hard: dev session] resulting tree:")
        _print_tree(None, by_parent, notes_by_id)

        # A one-off life note dropped mid-session should never get roped into
        # the project hierarchy, and nothing should attach itself under it.
        coffee_note = notes_by_id[coffee_id]
        print("[hard: dev session] coffee note parent:", coffee_note.parent_note_id)
        self.assertIsNone(coffee_note.parent_note_id)
        self.assertNotIn(coffee_id, by_parent)

        # The late bugfix note should ideally climb back into the character
        # thread (double-jump note or one of its ancestors) despite several
        # unrelated notes arriving in between — not guaranteed, but worth
        # seeing which way it leans.
        bugfix_note = notes_by_id[bugfix_id]
        print("[hard: dev session] bugfix parent:", bugfix_note.parent_note_id, "vs double_jump_id:", double_jump_id)

        # A healthy session should produce at least one grandchild (depth >= 2)
        # somewhere — if everything is flat, relationship nesting isn't doing
        # its job at all.
        max_depth = 0
        def _depth(note_id: int, current: int) -> int:
            deepest = current
            for child_id in by_parent.get(note_id, []):
                deepest = max(deepest, _depth(child_id, current + 1))
            return deepest
        for root_id in by_parent.get(None, []):
            max_depth = max(max_depth, _depth(root_id, 0))
        print("[hard: dev session] max nesting depth:", max_depth)
        self.assertGreaterEqual(max_depth, 1)


if __name__ == "__main__":
    unittest.main()
