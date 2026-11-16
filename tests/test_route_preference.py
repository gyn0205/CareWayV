"""Đổi tầng phải ưu tiên thang máy, thang bộ chỉ là phương án dự phòng."""

import unittest
from types import SimpleNamespace

from app.services.wayfinding import shortest_path


def edge(a, b, kind, seconds):
    return SimpleNamespace(from_node_id=a, to_node_id=b, kind=kind, cost_seconds=seconds)


class RoutePreferenceTest(unittest.TestCase):
    def test_prefers_elevator_even_when_stairs_are_faster(self):
        # Tầng 4 → tầng 3: thang bộ nhanh hơn nhưng vẫn phải chọn thang máy.
        edges = [
            edge("K4", "STAIRS4", "walk", 10), edge("STAIRS4", "STAIRS3", "stairs", 33),
            edge("STAIRS3", "ROOM3", "walk", 10),
            edge("K4", "LIFT4", "walk", 60), edge("LIFT4", "LIFT3", "elevator", 42),
            edge("LIFT3", "ROOM3", "walk", 60),
        ]
        seconds, path = shortest_path("K4", "ROOM3", edges)
        self.assertEqual([e.kind for e in path], ["walk", "elevator", "walk"])
        self.assertEqual(seconds, 162)  # thời gian thật, không cộng khoản phạt

    def test_prefers_elevator_across_many_floors(self):
        # Tầng 6 → tầng 3: thang máy đi thẳng, thang bộ phải qua từng tầng.
        edges = [edge(f"S{f}", f"S{f - 1}", "stairs", 33) for f in (6, 5, 4)]
        edges += [edge("K6", "S6", "walk", 5), edge("S3", "ROOM3", "walk", 5)]
        edges += [edge("K6", "L6", "walk", 90), edge("L6", "L3", "elevator", 70), edge("L3", "ROOM3", "walk", 90)]
        _, path = shortest_path("K6", "ROOM3", edges)
        self.assertNotIn("stairs", [e.kind for e in path])

    def test_falls_back_to_stairs_when_no_elevator_route(self):
        edges = [edge("K4", "S4", "walk", 10), edge("S4", "S3", "stairs", 33), edge("S3", "ROOM3", "walk", 10)]
        seconds, path = shortest_path("K4", "ROOM3", edges)
        self.assertIn("stairs", [e.kind for e in path])
        self.assertEqual(seconds, 53)


if __name__ == "__main__":
    unittest.main()
