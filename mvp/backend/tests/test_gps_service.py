"""GPS mock + location suggestion tests."""

import math
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import database
from services import gps_service, location_service, note_service


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6_371_000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


class GpsServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        database.DB_PATH = Path(self.temp_dir.name) / "test.db"
        database.init_db()
        gps_service.reset_state()
        gps_service.set_rng_seed(42)

    def tearDown(self):
        gps_service.reset_state()
        self.temp_dir.cleanup()

    def test_tick_without_locations_uses_default(self):
        coords = gps_service.tick(force=True)
        self.assertAlmostEqual(coords.latitude, gps_service.DEFAULT_LATITUDE, places=4)
        self.assertAlmostEqual(coords.longitude, gps_service.DEFAULT_LONGITUDE, places=4)
        self.assertIsNone(gps_service.get_active_location())

    def test_tick_near_saved_location_within_jitter(self):
        location = location_service.save_current_location("gym", 40.1, -8.2)
        published = []

        with patch("services.gps_service.event_bus.publish", side_effect=lambda *a, **k: published.append((a, k))):
            coords = gps_service.tick(force=True)

        active = gps_service.get_active_location()
        self.assertIsNotNone(active)
        self.assertEqual(active.id, location.id)
        distance = _haversine_m(location.latitude, location.longitude, coords.latitude, coords.longitude)
        self.assertGreaterEqual(distance, 40)
        self.assertLessEqual(distance, 200)
        self.assertTrue(any(args[0] == "gps_suggestions" for args, _kwargs in published))

    def test_suggestions_only_include_bound_active_notes(self):
        location = location_service.save_current_location("gym", 40.1, -8.2)
        other = location_service.save_current_location("home", 41.0, -8.0)
        bound_id, _ = note_service.save("stretch at the gym")
        other_id, _ = note_service.save("water plants at home")
        from database import update_note_location

        update_note_location(bound_id, location.id)
        update_note_location(other_id, other.id)

        suggestions = gps_service.get_location_suggestions(location.id)
        ids = {note.id for note in suggestions}
        self.assertIn(bound_id, ids)
        self.assertNotIn(other_id, ids)


if __name__ == "__main__":
    unittest.main()
