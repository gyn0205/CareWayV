"""Câu khách hỏi kiểu lễ tân: cấp cứu, gọi tắt, triệu chứng, nhà vệ sinh (cần PostgreSQL đã seed)."""

import unittest

from app.db.session import SessionLocal
from app.schema.wayfinding import TextTurn
from app.services.wayfinding import process_text_turn


class ReceptionistTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = cls.enterClassContext(SessionLocal())

    def ask(self, *texts):
        # Gửi lần lượt từng câu, mang context của lượt trước sang lượt sau như kiosk.
        context = None
        for text in texts:
            result = process_text_turn(self.db, TextTurn(kiosk_code="KIOSK-3", text=text, context=context))
            context = result.context
        return result

    def test_emergency_is_never_guessed(self):
        for texts in (("phòng cấp cứu",), ("I need emergency help",), ("Khám ung bướu", "cấp cứu")):
            with self.subTest(texts=texts):
                result = self.ask(*texts)
                self.assertEqual(result.status, "emergency")
                self.assertIn("115", result.message)
        self.assertEqual({c.name for c in self.ask("châm cứu").candidates}, {"Châm cứu A", "Châm cứu B"})

    def test_short_names(self):
        for text, codes in (
            ("cho tôi đến chỗ siêu âm tim", ["3-010"]), ("khám mắt", ["4-237"]),
            ("tôi cần đi khám tổng quát", ["4-08"]), ("I need the cardiology center", ["3-01"]),
            ("quầy thanh toán", ["3-10", "4-01"]), ("Where can I pay?", ["3-167", "4-001"]),
        ):
            with self.subTest(text=text):
                self.assertEqual([c.code for c in self.ask(text).candidates], codes)
        self.assertEqual(self.ask("quầy thanh toán tầng 4").route.destination.code, "4-01")
        self.assertEqual(self.ask("Tôi có hẹn khám sức khỏe tinh thần").route.destination.code, "3-05")

    def test_symptoms_without_appointment_go_to_advice_desk(self):
        for text in ("tôi bị đau đầu thì khám ở đâu", "con tôi bị sốt", "tôi chưa có lịch, bị chóng mặt", "I have a headache"):
            with self.subTest(text=text):
                result = self.ask(text)
                self.assertEqual(result.status, "route")
                self.assertEqual(result.route.destination.name, "Tư vấn dịch vụ và đặt lịch")
        # Đã có lịch thì không tự đưa đi quầy: hỏi mã phòng trên phiếu.
        self.assertEqual(self.ask("tôi có hẹn rồi nhưng bị đau đầu").status, "not_found")
        # "ở đâu" bỏ dấu là "o dau" — không được coi là triệu chứng.
        self.assertEqual(self.ask("nhà thuốc ở đâu").route.destination.code, "3-04")

    def test_nearest_restroom(self):
        for texts in (("nhà vệ sinh ở đâu",), ("Where is the toilet?",), ("Khám ung bướu", "nhà vệ sinh ở đâu")):
            with self.subTest(texts=texts):
                route = self.ask(*texts).route
                self.assertEqual((route.destination.code, route.destination.floor), ("WC-B", 3))

    def test_english_doctor_choices_name_departments(self):
        result = self.ask("I have an appointment with doctor Nguyen Van Hung")
        self.assertIn("Center for Orthopaedic and Sports Medicine", result.message)
        self.assertEqual(self.ask("I have an appointment with doctor Nguyen Van Hung", "orthopedics").route.destination.code, "3-108")


if __name__ == "__main__":
    unittest.main()
