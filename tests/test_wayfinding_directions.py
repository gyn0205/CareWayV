"""Câu chỉ đường kiểu lễ tân: rẽ trái/phải theo hướng người đi, gộp đoạn thẳng, kèm mốc."""

import unittest
from types import SimpleNamespace

from app.schema.wayfinding import Point
from app.services.wayfinding_directions import compose_steps

POINTS = {1: (0.5, 0.7), 2: (0.56, 0.7), 3: (0.56, 0.5), 4: (0.56, 0.2), 5: (0.5, 0.2)}


def point(node):
    x, y = POINTS[node]
    return Point(floor_id=1, floor=4, x=x, y=y, label=None, map_asset_url=None)


def walk(a, b, seconds, phrase):
    return SimpleNamespace(
        from_node_id=a, to_node_id=b, kind="walk", cost_seconds=seconds, instruction=phrase, instruction_en=phrase,
    )


class ComposeStepsTest(unittest.TestCase):
    def test_turns_follow_the_walker_not_the_map(self):
        # Khách đứng nhìn lên (bắc): sang phải, rẽ trái đi lên qua thang máy, cuối cùng rẽ trái vào phòng.
        route = [
            walk(1, 2, 7, "sang phía bên kia hành lang"), walk(2, 3, 22, "qua Thang máy A"),
            walk(3, 4, 30, ""), walk(4, 5, 6, "đến phòng 4-005 — Khám tai"),
        ]
        steps = compose_steps(route, point, False, (0.0, -1.0))
        self.assertEqual([step.instruction for step in steps], [
            "Từ đây, anh chị rẽ phải sang phía bên kia hành lang.",
            "Rẽ trái, đi thẳng khoảng 50 m, qua Thang máy A.",
            "Rẽ trái là đến phòng 4-005 — Khám tai.",
        ])
        # Hai đoạn thẳng hàng gộp làm một bước, vẫn nối liền để vẽ sơ đồ.
        self.assertEqual(steps[1].seconds, 52)
        self.assertTrue(all(a.end == b.start for a, b in zip(steps, steps[1:])))

    def test_facing_the_other_way_flips_the_first_turn(self):
        steps = compose_steps([walk(1, 2, 7, "across to the other side of the corridor")], point, True, (0.0, 1.0))
        self.assertEqual(steps[0].instruction, "From here, turn left across to the other side of the corridor.")
