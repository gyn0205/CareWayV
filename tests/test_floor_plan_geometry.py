"""Kiểm tra mặt bằng tầng 3–4 (vẽ theo bảng thật) mà không cần cơ sở dữ liệu."""

import heapq
import unittest
from collections import defaultdict

from app.db.seeds.vinmec_floors_3_4.catalog import ZONES
from app.db.seeds.vinmec_floors_3_4.floor_plan import demo_floor_plan
from app.db.seeds.vinmec_floors_3_4.geometry import EXITS, HALL, SHAPES, SUNROOMS
from app.db.seeds.vinmec_floors_3_4.layout import build_layout, room_slots


def inside(polygon, x, y):
    """Điểm nằm trong hoặc trên cạnh đa giác vuông góc."""
    crossing = False
    for (x1, y1), (x2, y2) in zip(polygon, polygon[1:] + polygon[:1]):
        if x1 == x2 == x and min(y1, y2) <= y <= max(y1, y2):
            return True
        if y1 == y2 == y and min(x1, x2) <= x <= max(x1, x2):
            return True
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            crossing = not crossing
    return crossing


def overlap(a, b):
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return ax < bx + bw and ax + aw > bx and ay < by + bh and ay + ah > by


class FloorPlanGeometryTest(unittest.TestCase):
    def test_every_department_from_the_wall_sign_has_a_shape(self):
        self.assertEqual({zone.code for zone in ZONES}, set(SHAPES))
        for level, count in ((3, 12), (4, 13)):
            plan = demo_floor_plan(level * 10, level)
            signed = [zone for zone in plan.zones if zone.number is not None]
            self.assertEqual(sorted(zone.number for zone in signed), list(range(1, count + 1)))
            self.assertTrue(all(zone.tone in ("orange", "green") and zone.outline for zone in signed))

    def test_reception_desk_fills_most_of_the_health_checkup_entrance_with_a_way_in_on_each_side(self):
        desk, checkup = SHAPES["4-14"], SHAPES["4-08"]
        dx, dy, dw, dh = desk.bounds
        _, cy, _, ch = checkup.bounds
        # Quầy chiếm hơn nửa mặt tiền (cạnh giáp hành lang) của khu KSK và quay ra hành lang.
        self.assertGreater(dh / ch, 0.5)
        self.assertEqual(dx + dw, HALL[0])
        # Hai lối vào KSK nằm ở hai bên quầy.
        doors = [checkup.path[0], checkup.side_door[0]]
        self.assertTrue(any(y < dy for _, y in doors))
        self.assertTrue(any(y > dy + dh for _, y in doors))
        self.assertTrue(all(x == HALL[0] for x, _ in doors))
        # Quầy không có số trên bảng, đi tới được và dẫn vào khu KSK từ cả hai lối.
        plan = demo_floor_plan(40, 4)
        [zone] = [zone for zone in plan.zones if zone.code == "4-14"]
        self.assertIsNone(zone.number)
        self.assertEqual(zone.tone, "desk")
        layout = build_layout()
        self.assertIn((4, "ENTRY-4-14"), layout.nodes)
        joined = {edge.destination for edge in layout.edges if edge.origin == (4, "DOOR-4-08-2-1")}
        self.assertIn((4, "PATH-4-08-2"), joined)

    def test_rooms_fit_inside_their_department_without_overlapping(self):
        for zone in ZONES:
            outline = list(SHAPES[zone.code].outline)
            rects = []
            for slot in room_slots(zone):
                x, y, width, height = slot.rect
                with self.subTest(room=slot.code):
                    for corner in ((x, y), (x + width, y), (x, y + height), (x + width, y + height)):
                        self.assertTrue(inside(outline, *corner))
                    self.assertFalse(any(overlap(slot.rect, other) for other in rects))
                    self.assertFalse(any(overlap(slot.rect, sun) for sun in SUNROOMS[zone.floor]))
                    self.assertFalse(overlap(slot.rect, (HALL[0], HALL[1], HALL[2] - HALL[0], HALL[3] - HALL[1])))
                rects.append(slot.rect)

    def test_departments_do_not_overlap_each_other_or_the_corridor(self):
        for level in (3, 4):
            zones = [zone for zone in ZONES if zone.floor == level]
            for zone in zones:
                x, y, width, height = SHAPES[zone.code].rooms
                center = (x + width / 2, y + height / 2)
                for other in zones:
                    if other is not zone:
                        self.assertFalse(inside(list(SHAPES[other.code].outline), *center), (zone.code, other.code))

    def test_every_room_is_reachable_from_all_four_kiosks_and_doors_match_the_plan(self):
        layout = build_layout()
        neighbors = defaultdict(list)
        for edge in layout.edges:
            neighbors[edge.origin].append((edge.destination, edge.cost))
            self.assertGreater(edge.cost, 0)
        kiosks = [key for key in layout.nodes if key[1].startswith("KIOSK")]
        self.assertEqual(len(kiosks), 4)
        for start in kiosks:
            distance = {start: 0}
            frontier = [(0, start)]
            while frontier:
                cost, node = heapq.heappop(frontier)
                if cost > distance[node]:
                    continue
                for target, step in neighbors[node]:
                    if cost + step < distance.get(target, float("inf")):
                        distance[target] = cost + step
                        heapq.heappush(frontier, (cost + step, target))
            self.assertEqual(set(layout.nodes) - set(distance), set(), start)
        for zone in ZONES:
            for slot in room_slots(zone):
                point = layout.nodes[zone.floor, slot.code]
                x, y, width, height = slot.rect
                self.assertEqual(point.x, x + width / 2)
                self.assertEqual(point.y, y + height if slot.bank < 0 else y)

    def test_atrium_stairs_sit_at_the_bottom_of_the_atrium_on_both_floors(self):
        layout = build_layout()
        stairs = {}
        for level in (3, 4):
            plan = demo_floor_plan(level * 10, level)
            [mark] = [landmark for landmark in plan.landmarks if landmark.kind == "stairs"]
            [steps] = [block for block in plan.blocks if block.kind == "escalator"]
            [void] = [block for block in plan.blocks if block.kind == "void"]
            node = layout.nodes[level, "STAIRS"]
            # Mốc vẽ trên bản đồ trùng nút điều hướng và nằm trong khối bậc thang.
            self.assertEqual((node.x, node.y), (mark.x, mark.y))
            self.assertTrue(steps.x <= mark.x <= steps.x + steps.width)
            self.assertTrue(steps.y <= mark.y <= steps.y + steps.height)
            stairs[level] = (mark.y - void.y) / void.height
        self.assertGreater(stairs[3], 0.6)
        self.assertGreater(stairs[4], 0.6)

    def test_each_floor_has_two_map_boards_facing_the_atrium(self):
        for level in (3, 4):
            plan = demo_floor_plan(level * 10, level)
            boards = [block for block in plan.blocks if block.kind == "board"]
            lifts = [block for block in plan.blocks if block.kind == "lift"]
            [void] = [block for block in plan.blocks if block.kind == "void"]
            self.assertEqual(len(boards), 2)
            for board in boards:
                with self.subTest(floor=level, board=board.y):
                    # Bảng nằm sát mép giếng sảnh (cách tối đa 4 đơn vị), không chạm thang máy.
                    gap_to_void = min(abs(board.y - (void.y + void.height)), abs(void.y - (board.y + board.height)))
                    self.assertLessEqual(gap_to_void, 4)
                    self.assertFalse(any(
                        board.y < lift.y + lift.height + 8 and board.y + board.height + 8 > lift.y
                        for lift in lifts
                    ))
            # Mỗi thang có đúng một bảng, ở đầu quay về giếng sảnh.
            self.assertEqual(sorted(board.y < void.y for board in boards), [False, True])

    def test_each_map_board_has_its_own_kiosk(self):
        layout = build_layout()
        for level in (3, 4):
            plan = demo_floor_plan(level * 10, level)
            boards = [block for block in plan.blocks if block.kind == "board"]
            kiosks = [mark for mark in plan.landmarks if mark.kind == "kiosk"]
            self.assertEqual(len(kiosks), len(boards))
            for board in boards:
                with self.subTest(floor=level, board=board.y):
                    # Đúng một kiosk đứng cách bảng không quá 15 đơn vị (theo chiều dọc).
                    near = [k for k in kiosks if abs(k.y - (board.y + board.height / 2)) <= 15]
                    self.assertEqual(len(near), 1)
                    # Mốc vẽ trên bản đồ trùng nút điều hướng của kiosk.
                    [code] = [k.code for k in near]
                    node = layout.nodes[level, code]
                    self.assertEqual((node.x, node.y), (near[0].x, near[0].y))

    def test_exit_signs_hang_on_an_outer_wall_without_covering_rooms(self):
        for level, signs in EXITS.items():
            zones = [zone for zone in ZONES if zone.floor == level]
            outlines = [list(SHAPES[zone.code].outline) for zone in zones]
            rooms = [slot.rect for zone in zones for slot in room_slots(zone)]
            for x, y in signs:
                with self.subTest(floor=level, sign=(x, y)):
                    sign = (x - 19, y - 8, 38, 16)
                    self.assertFalse(any(overlap(sign, room) for room in rooms))
                    # Biển chạm một khu (cách mép không quá ~25 đơn vị).
                    probes = [(x + dx, y + dy) for dx in (-25, 0, 25) for dy in (-14, 0, 14)]
                    self.assertTrue(any(inside(outline, *probe) for outline in outlines for probe in probes))


if __name__ == "__main__":
    unittest.main()
