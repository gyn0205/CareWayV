"""Hiểu câu trả lời ngắn của khách và khớp gần đúng khi STT nghe sai (không cần database)."""

import unittest
from collections import namedtuple

from app.services.wayfinding_language import appointment_answer, stated_appointment, yes_no
from app.services.wayfinding_lookup import fuzzy_matches, match_doctors


class YesNoTest(unittest.TestCase):
    def test_answers(self):
        for text, expected in (
            ("Đúng rồi", True), ("vâng", True), ("Dạ phải", True), ("có", True), ("Yes", True),
            ("ok", True), ("Không phải", False), ("không đúng", False), ("sai rồi", False),
            ("No", False), ("chưa", False), ("điện tâm đồ", None), ("ờ", None), ("tầng 3", None),
        ):
            with self.subTest(text=text):
                self.assertIs(yes_no(text), expected)


class AppointmentTest(unittest.TestCase):
    def test_stated_in_the_question(self):
        for text, expected in (
            ("Tôi có hẹn khám ở khoa tim", True), ("tôi đã đặt lịch rồi", True), ("bác sĩ hẹn tôi", True),
            ("I have an appointment at cardiology", True), ("tôi chưa có lịch hẹn", False),
            ("Tôi chưa đặt lịch, khoa nội tiết ở đâu", False), ("I don't have an appointment", False),
            ("Khoa tim mạch ở đâu", None), ("tôi muốn đặt lịch khám", None), ("I want to book a visit", None),
        ):
            with self.subTest(text=text):
                self.assertIs(stated_appointment(text), expected)

    def test_answers_to_the_question(self):
        for text, expected in (
            ("Đã đặt lịch", True), ("rồi", True), ("có", True), ("dạ có rồi", True), ("không, tôi đặt rồi", True),
            ("Yes, I have one", True), ("yes I do", True), ("Chưa đặt lịch", False), ("chưa", False),
            ("dạ không", False), ("không có", False), ("Not yet", False), ("no I don't", False), ("ờ", None),
        ):
            with self.subTest(text=text):
                self.assertIs(appointment_answer(text), expected)


class DoctorMatchTest(unittest.TestCase):
    Doc = namedtuple("Doc", "code normalized_name")
    DOCTORS = [Doc("A", "nguyen van an"), Doc("B", "tran thi an"), Doc("C", "le minh nam")]

    def test_full_name_beats_given_name(self):
        for text, expected in (
            ("bác sĩ Nguyễn Văn An", ["A"]), ("Nguyễn Văn An", ["A"]), ("bác sĩ An", ["A", "B"]),
            ("bác sỹ Văn An", ["A"]), ("Dr. Nam", ["C"]), ("doctor tran thi an", ["B"]),
        ):
            with self.subTest(text=text):
                self.assertEqual([d.code for d in match_doctors(text, self.DOCTORS)], expected)

    def test_given_name_alone_needs_the_word_doctor(self):
        # "an", "nam" là chữ thường gặp ("an toàn", "miền Nam") → không có "bác sĩ" thì không tính.
        for text in ("tôi ở miền Nam", "đi an toàn", "khoa tim mạch"):
            with self.subTest(text=text):
                self.assertEqual(match_doctors(text, self.DOCTORS), [])


class FuzzyMatchTest(unittest.TestCase):
    PHRASES = {
        "dien tam do": {"ECG"}, "tim mach": {"CARDIO"}, "soi da day": {"GASTRO"},
        "giam dau": {"PAIN"}, "kham tui mat": {"GALL"}, "nha thuoc": {"PHARMACY"},
    }

    def test_one_misheard_word_with_same_first_letter(self):
        for query, expected in (
            ("toi muon lam dien tim do", {"ECG"}),
            ("chi toi den khoa tim mat", {"CARDIO"}),
            ("nha thuot o dau", {"PHARMACY"}),
        ):
            with self.subTest(query=query):
                self.assertEqual(fuzzy_matches(query, self.PHRASES), expected)

    def test_everyday_chatter_does_not_match(self):
        # "tôi đã đặt" ≈ "soi dạ dày" và "tìm đâu" ≈ "giảm đau" theo ký tự, nhưng lệch chữ đầu / nhiều chữ.
        for query in ("toi da dat lich roi", "tim dau roi", "xin chao", "dung roi", "khong phai"):
            with self.subTest(query=query):
                self.assertEqual(fuzzy_matches(query, self.PHRASES), set())


if __name__ == "__main__":
    unittest.main()
