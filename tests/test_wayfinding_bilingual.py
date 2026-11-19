"""Exercise both HTTP endpoints with seeded PostgreSQL and a mocked OpenRouter transport."""

import base64
import io
import json
import socket
import unittest
import wave
from threading import Thread
from time import monotonic, sleep
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

import uvicorn
from pydantic import SecretStr

from app.core.config import settings
from app.main import app


def wav_fixture():
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as audio:
        audio.setparams((1, 2, 16_000, 0, "NONE", "not compressed"))
        audio.writeframes(bytes(8_000))
    return base64.b64encode(buffer.getvalue()).decode("ascii")


class BilingualWayfindingTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.openrouter = cls.enterClassContext(patch("app.services.openrouter.urlopen"))
        cls.enterClassContext(patch.object(settings, "OPENROUTER_API_KEY", SecretStr("mock-key")))
        cls.enterClassContext(patch.object(settings, "ELEVENLABS_API_KEY", None))
        cls.enterClassContext(patch.object(settings, "OPENROUTER_STT_MODEL", "openai/whisper-large-v3-turbo"))
        cls.enterClassContext(patch.object(settings, "OPENROUTER_TTS_MODEL", "elevenlabs/eleven-flash-v2.5"))

        listener = cls.enterClassContext(socket.socket())
        listener.bind(("127.0.0.1", 0))
        prefix = settings.API_V1_PREFIX + settings.WAYFINDING_PREFIX
        cls.base = f"http://127.0.0.1:{listener.getsockname()[1]}{prefix}"
        cls.server = uvicorn.Server(uvicorn.Config(app, log_level="error", ws="none"))
        cls.thread = Thread(target=cls.server.run, kwargs={"sockets": [listener]}, daemon=True)
        cls.addClassCleanup(cls.stop_server)
        cls.thread.start()
        deadline = monotonic() + 8
        while not cls.server.started and cls.thread.is_alive() and monotonic() < deadline:
            sleep(0.01)
        if not cls.server.started:
            raise RuntimeError("Could not start the local test server")

    @classmethod
    def stop_server(cls):
        cls.server.should_exit = True
        cls.thread.join(timeout=8)

    def setUp(self):
        self.openrouter.reset_mock(side_effect=True)

    def submit(self, endpoint, **payload):
        request = Request(
            f"{self.base}/{endpoint}",
            data=json.dumps({"kiosk_code": "KIOSK-3", **payload}).encode(),
            headers={"Content-Type": "application/json"},
        )
        try:
            with urlopen(request, timeout=10) as response:
                return response.status, json.load(response)
        except HTTPError as error:
            with error:
                return error.code, json.load(error)

    def assert_route(self, result, code, language, elevator=False):
        self.assertEqual(result["language"], language)
        self.assertEqual(result["status"], "route")
        route = result["route"]
        self.assertEqual(route["destination"]["code"], code)
        steps = route["steps"]
        self.assertEqual(steps[0]["start"], route["origin"])
        self.assertEqual(steps[-1]["end"], route["arrival"])
        self.assertEqual(route["seconds"], sum(step["seconds"] for step in steps))
        self.assertTrue(all(a["end"] == b["start"] for a, b in zip(steps, steps[1:])))
        if elevator:
            [vertical] = [step for step in steps if step["kind"] != "walk"]
            self.assertEqual(vertical["kind"], "elevator")
            self.assertEqual([vertical["start"]["floor"], vertical["end"]["floor"]], [3, 4])
            self.assertIn("elevator" if language == "en" else "Thang máy", vertical["instruction"])

    def with_appointment(self, result, answer=None):
        """Kiosk hỏi "đã đặt lịch chưa" → trả lời là đã có lịch, trả về lượt kế tiếp."""
        self.assertEqual(result["status"], "clarify")
        self.assertEqual(result["context"]["pending"], "appointment")
        answer = answer or ("Yes, I have one" if result["language"] == "en" else "Đã đặt lịch")
        status, turn = self.submit("text", text=answer, context=result["context"])
        self.assertEqual(status, 200)
        return turn

    def test_text_departments_and_service_aliases(self):
        for utterance, code, language, asks in (
            ("Where is the Cardiovascular Center?", "3-01", "en", True),
            ("Chỉ đường đến Trung tâm Tim mạch", "3-01", "vi", True),
            ("Where can I get an electrocardiogram?", "3-009", "en", True),
            ("Tôi muốn đo điện tim", "3-009", "vi", True),
            # STT realtime viết liền mã phòng; đọc mã phòng = đã có phiếu → không hỏi lịch hẹn.
            ("Phòng 4053 ở đâu vậy?", "4-053", "vi", False),
            ("Cho tôi đến nhà thuốc. À không, phòng 4053.", "4-053", "vi", False),
        ):
            with self.subTest(utterance=utterance):
                status, result = self.submit("text", text=utterance)
                self.assertEqual(status, 200)
                self.assert_route(self.with_appointment(result) if asks else result, code, language)
        self.openrouter.assert_not_called()

    def test_appointment_is_asked_before_clinics(self):
        status, first = self.submit("text", text="Khoa tim mạch ở đâu?")
        self.assertEqual(first["message"], "Anh chị đã đặt lịch hẹn ở Trung tâm Tim mạch chưa ạ?")
        self.assertEqual(first["replies"], ["Đã đặt lịch", "Chưa đặt lịch"])
        for answer in ("Đã đặt lịch", "rồi", "có", "Dạ có rồi", "không, tôi đặt rồi"):
            with self.subTest(answer=answer):
                self.assert_route(self.with_appointment(first, answer), "3-01", "vi")

        # Chưa có lịch → mời đến quầy tư vấn tầng 4, kèm hai lựa chọn.
        for answer in ("Chưa đặt lịch", "chưa", "Dạ không", "không có"):
            with self.subTest(answer=answer):
                status, offer = self.submit("text", text=answer, context=first["context"])
                self.assertEqual(offer["status"], "clarify")
                self.assertIn("tầng 4", offer["message"])
                self.assertIn("vẫn muốn đến Trung tâm Tim mạch", offer["message"])
                desk, wanted = [candidate["code"] for candidate in offer["candidates"]]
                self.assertEqual(wanted, "3-01")
                self.assertEqual(offer["context"]["pending"], "booking")
        for answer, code in (
            ("Đến quầy tư vấn", desk), ("ok tôi ra quầy", desk), (desk, desk),
            ("Tôi vẫn muốn đến khoa", "3-01"), ("cứ chỉ đường cho tôi", "3-01"), ("3-01", "3-01"),
        ):
            with self.subTest(answer=answer):
                status, turn = self.submit("text", text=answer, context=offer["context"])
                self.assert_route(turn, code, "vi")
        # Câu đáp không hiểu → hỏi lại đúng câu đang chờ.
        status, again = self.submit("text", text="ờ", context=offer["context"])
        self.assertEqual(again["context"]["pending"], "booking")
        status, again = self.submit("text", text="ờ", context=first["context"])
        self.assertEqual(again["message"], first["message"])

    def test_appointment_not_asked_for_walk_in_or_stated(self):
        for utterance, code in (
            ("Nhà thuốc ở đâu", "3-04"), ("quầy lễ tân", "4-243"), ("nộp mẫu nước tiểu tầng 4", None),
            ("Tôi có hẹn khám ở trung tâm tim mạch", "3-01"), ("bác sĩ hẹn tôi đo điện tim", "3-009"),
        ):
            with self.subTest(utterance=utterance):
                status, result = self.submit("text", text=utterance)
                if code is None:
                    # Nhiều phòng nộp mẫu trên tầng 4 → chọn phòng, rồi đi luôn không hỏi lịch hẹn.
                    self.assertEqual(result["status"], "clarify")
                    code = result["candidates"][0]["code"]
                    status, result = self.submit("text", text=code, context=result["context"])
                self.assert_route(result, code, "vi")
        # Tự nói chưa có lịch → mời ngay đến quầy tư vấn, không hỏi lại.
        status, offer = self.submit("text", text="Tôi chưa đặt lịch, khoa nội tiết ở đâu")
        self.assertEqual(offer["context"]["pending"], "booking")
        # English: chưa có lịch → quầy tư vấn hoặc vẫn đến khoa.
        status, first = self.submit("text", text="Where is the Cardiovascular Center?")
        self.assertEqual(first["replies"], ["Yes, I have one", "Not yet"])
        status, offer = self.submit("text", text="Not yet", context=first["context"])
        self.assertIn("still go to Cardiovascular Center", offer["message"])
        desk = offer["candidates"][0]["code"]
        for answer, code in (("I still want to go there", "3-01"), ("OK, the advice desk", desk)):
            with self.subTest(answer=answer):
                status, turn = self.submit("text", text=answer, context=offer["context"])
                self.assert_route(turn, code, "en")

    def test_appointment_asked_after_choosing_among_candidates(self):
        # "siêu âm vú" có 2 phòng → bấm chọn một phòng → vẫn phải hỏi lịch hẹn (không phải khách đọc mã).
        status, first = self.submit("text", text="siêu âm vú")
        self.assertEqual(first["status"], "clarify")
        code = first["candidates"][0]["code"]
        status, turn = self.submit("text", text=code, context=first["context"])
        self.assert_route(self.with_appointment(turn), code, "vi")
        # Đã nói có lịch từ đầu thì sau khi chọn phòng không hỏi lại.
        status, first = self.submit("text", text="tôi có lịch siêu âm vú")
        self.assertIs(first["context"]["appointment"], True)
        status, turn = self.submit("text", text=code, context=first["context"])
        self.assert_route(turn, code, "vi")

    def test_misheard_name_is_confirmed_before_routing(self):
        # STT nghe "điện tâm đồ" thành "điện tim đồ" → hỏi lại, đồng ý (nói hoặc bấm thẻ) mới chỉ đường.
        status, first = self.submit("text", text="Tôi muốn làm điện tim đồ")
        self.assertEqual(status, 200)
        self.assertEqual((first["status"], first["language"]), ("clarify", "vi"))
        self.assertEqual(first["message"], "Có phải anh chị muốn đến Điện tâm đồ không?")
        self.assertEqual(first["replies"], ["Đúng rồi", "Không phải"])
        self.assertEqual([c["code"] for c in first["candidates"]], ["3-009"])
        self.assertEqual(first["context"]["pending"], "confirm")
        for answer in ("Đúng rồi", "vâng", "3-009"):
            with self.subTest(answer=answer):
                status, turn = self.submit("text", text=answer, context=first["context"])
                self.assertEqual(status, 200)
                self.assert_route(self.with_appointment(turn), "3-009", "vi")

        # Từ chối → mời nói lại, không giữ câu xác nhận cũ.
        status, turn = self.submit("text", text="Không phải", context=first["context"])
        self.assertEqual((turn["status"], turn["context"]), ("not_found", None))
        self.assertIn("nói lại", turn["message"])
        # Đổi ý giữa chừng → tìm điểm đến mới.
        status, turn = self.submit("text", text="Không, tôi cần đến nhà thuốc", context=first["context"])
        self.assert_route(turn, "3-04", "vi")

    def test_misheard_name_in_english_and_chatter(self):
        status, first = self.submit("text", text="Where is the cardiovasculer center?")
        self.assertEqual((first["status"], first["language"]), ("clarify", "en"))
        self.assertEqual(first["message"], "Did you mean Cardiovascular Center?")
        self.assertEqual(first["replies"], ["Yes", "No"])
        status, turn = self.submit("text", text="Yes", context=first["context"])
        self.assert_route(self.with_appointment(turn), "3-01", "en")
        # Câu nói chuyện thường không bị đoán thành một phòng.
        for chatter in ("Trời hôm nay nóng quá", "Tôi đã đặt lịch rồi", "Tìm đâu rồi"):
            with self.subTest(chatter=chatter):
                status, turn = self.submit("text", text=chatter)
                self.assertEqual(turn["status"], "not_found")

    def test_short_department_names(self):
        # Khách gọi tắt tên khoa nhiều vế.
        for utterance, code in (
            ("Khoa nội tiết ở đâu", "4-07"), ("Trung tâm ung bướu", "3-03"),
            ("khoa thần kinh", "4-10"), ("tai mũi họng", "4-13"),
        ):
            with self.subTest(utterance=utterance):
                status, result = self.submit("text", text=utterance)
                self.assert_route(self.with_appointment(result), code, "vi")

    def test_doctor_with_duplicate_names_in_different_departments(self):
        # 3 bác sĩ "Nguyễn Văn Hùng" ở 3 khoa → hỏi khoa → chỉ đường, câu chỉ đường nêu đúng bác sĩ.
        status, first = self.submit("text", text="Tôi có lịch hẹn với bác sĩ Nguyễn Văn Hùng")
        self.assertEqual(first["status"], "clarify")
        self.assertEqual(len(first["candidates"]), 3)
        self.assertTrue(all(c["doctor"].endswith("Nguyễn Văn Hùng") for c in first["candidates"]))
        self.assertIn("ở khoa nào", first["message"])
        self.assertIs(first["context"]["appointment"], True)
        cardio = next(c for c in first["candidates"] if c["department"] == "Trung tâm Tim mạch")
        for answer in ("khoa tim mạch", "Trung tâm Tim mạch", cardio["code"]):
            with self.subTest(answer=answer):
                status, turn = self.submit("text", text=answer, context=first["context"])
                # Đã nói có lịch hẹn → không hỏi lại.
                self.assert_route(turn, cardio["code"], "vi")
                self.assertTrue(turn["message"].startswith(f"Để gặp {cardio['doctor']} tại"))
                self.assertEqual(turn["route"]["destination"]["doctor"], cardio["doctor"])
        # Trả lời bằng tầng: tầng 4 chỉ có một người.
        status, turn = self.submit("text", text="tầng 4", context=first["context"])
        self.assertEqual(turn["route"]["destination"]["floor"], 4)

    def test_doctor_twins_in_one_department_and_given_name_only(self):
        # Hai "Lê Minh Tuấn" cùng khoa → phân biệt bằng học hàm và phòng.
        status, first = self.submit("text", text="Tôi có hẹn với bác sĩ Lê Minh Tuấn")
        self.assertIn("đọc mã phòng", first["message"])
        doctors = {c["doctor"] for c in first["candidates"]}
        self.assertEqual(len(doctors), 2)
        chosen = first["candidates"][1]
        status, turn = self.submit("text", text=chosen["code"], context=first["context"])
        self.assert_route(turn, chosen["code"], "vi")
        self.assertIn(chosen["doctor"], turn["message"])
        # Chỉ nói tên gọi → nhiều người → xin họ tên đầy đủ, kèm thẻ chọn.
        status, first = self.submit("text", text="Tôi có hẹn với bác sĩ Hùng")
        self.assertIn("họ tên đầy đủ", first["message"])
        self.assertGreater(len(first["candidates"]), 4)
        status, turn = self.submit("text", text="bác sĩ Hoàng Quốc Việt tầng 3", context=first["context"])
        self.assertEqual(turn["route"]["destination"]["floor"], 3)

    def test_doctor_without_appointment_and_in_english(self):
        # Hỏi bác sĩ mà chưa nói lịch hẹn → vẫn hỏi lịch hẹn, nêu tên bác sĩ; câu chỉ đường cuối vẫn nhớ bác sĩ.
        status, first = self.submit("text", text="bác sĩ Đỗ Thị Hương tầng 4 ở đâu")
        self.assertEqual(first["message"], f"Anh chị đã đặt lịch hẹn với {first['candidates'][0]['doctor']} chưa ạ?")
        status, turn = self.submit("text", text="rồi", context=first["context"])
        self.assertIn("Đỗ Thị Hương", turn["message"])
        status, first = self.submit("text", text="I have an appointment with doctor Pham Thu Ha")
        self.assertEqual((first["status"], first["language"]), ("clarify", "en"))
        self.assertIn("in Endoscopy Unit, floor 4", first["message"])
        code = first["candidates"][0]["code"]
        status, turn = self.submit("text", text=code, context=first["context"])
        self.assert_route(turn, code, "en")
        self.assertTrue(turn["message"].startswith("To see "))

    def test_appointment_question_keeps_destination_on_map(self):
        # Bản đồ cần biết điểm đến để mở đúng tầng trong lúc hỏi lịch hẹn.
        status, first = self.submit("text", text="khoa tim mạch")
        self.assertEqual(first["context"]["pending"], "appointment")
        self.assertEqual([c["code"] for c in first["candidates"]], ["3-01"])
        # Mã khoa nội bộ không lộ ra API.
        self.assertNotIn("department_code", first["candidates"][0])

    def test_kiosk_map_shows_every_floor_before_any_question(self):
        # Màn hình chờ: kiosk đứng đúng tầng và có mặt bằng cả hai tầng, tầng cao trước.
        with urlopen(f"{self.base}/kiosks/KIOSK-4", timeout=10) as response:
            result = json.load(response)
        self.assertEqual(result["origin"]["floor"], 4)
        self.assertEqual([floor["floor"] for floor in result["floors"]], [4, 3])
        self.assertEqual(
            {plan["floor_id"] for plan in result["floor_plans"]},
            {floor["floor_id"] for floor in result["floors"]},
        )
        with self.assertRaises(HTTPError) as missing:
            urlopen(f"{self.base}/kiosks/NO-KIOSK?language=en", timeout=10)
        with missing.exception as error:
            self.assertEqual(error.code, 404)
            self.assertEqual(json.load(error)["detail"], "No active kiosk found.")

    def test_all_four_kiosks_start_at_their_own_map_board(self):
        origins = {}
        kiosks = (("KIOSK-3-A", 3), ("KIOSK-3", 3), ("KIOSK-4-A", 4), ("KIOSK-4", 4))
        for (code, floor), room in ((kiosk, room) for kiosk in kiosks for room in ("3-167", "4-053")):
            with self.subTest(kiosk=code, room=room):
                status, result = self.submit("text", kiosk_code=code, text=room)
                self.assertEqual(status, 200)
                self.assert_route(result, room, "vi")
                # Không đọc lặp một câu cho cùng một lối đi thẳng (vd. "Băng ngang hành lang…" hai lần).
                steps = result["route"]["steps"]
                self.assertFalse(any(
                    a["instruction"] == b["instruction"] and a["start"]["y"] == a["end"]["y"] == b["end"]["y"]
                    for a, b in zip(steps, steps[1:])
                ))
                origin = result["route"]["origin"]
                self.assertEqual(origin["floor"], floor)
                # Điểm xuất phát trùng mốc kiosk vẽ trên mặt bằng tầng đó.
                plan = next(p for p in result["route"]["floor_plans"] if p["floor_id"] == origin["floor_id"])
                self.assertTrue(any(
                    mark["kind"] == "kiosk"
                    and abs(origin["x"] * plan["width"] - mark["x"]) < 1e-6
                    and abs(origin["y"] * plan["height"] - mark["y"]) < 1e-6
                    for mark in plan["landmarks"]
                ))
                origins[code] = (origin["floor"], origin["x"], origin["y"])
        self.assertEqual(len(set(origins.values())), 4)

    def test_cashier_route_fits_the_floor_plans_on_both_sides_of_the_elevator(self):
        status, result = self.submit(
            "text", kiosk_code="KIOSK-4", text="3-167", wheelchair=True,
        )
        self.assertEqual(status, 200)
        self.assert_route(result, "3-167", "vi")
        route = result["route"]
        [transfer] = [step for step in route["steps"] if step["start"]["floor_id"] != step["end"]["floor_id"]]
        self.assertEqual(transfer["kind"], "elevator")
        upper, lower = route["floor_plans"]
        self.assertEqual(
            [upper["floor_id"], lower["floor_id"]],
            [route["origin"]["floor_id"], route["arrival"]["floor_id"]],
        )
        for plan, point in ((upper, transfer["start"]), (lower, transfer["end"])):
            self.assertTrue(any(
                landmark["kind"] == "elevator"
                and abs(point["x"] * plan["width"] - landmark["x"]) < 1e-6
                and abs(point["y"] * plan["height"] - landmark["y"]) < 1e-6
                for landmark in plan["landmarks"]
            ))
        [room] = [room for room in lower["rooms"] if room["code"] == "3-167"]
        arrival = route["arrival"]
        self.assertEqual(room["door_side"], "south")
        self.assertAlmostEqual(arrival["x"] * lower["width"], room["x"] + room["width"] / 2)
        self.assertAlmostEqual(arrival["y"] * lower["height"], room["y"] + room["height"])

    def test_english_clarification_keeps_language_and_accessibility(self):
        status, first = self.submit("text", text="Where can I pay my bill? I use a wheelchair.")
        self.assertEqual(status, 200)
        self.assertEqual((first["status"], first["language"]), ("clarify", "en"))
        self.assertTrue(first["context"]["wheelchair"])
        for answer in ("On the fourth floor, please", "On floor four", "4th floor"):
            with self.subTest(answer=answer):
                status, turn = self.submit("text", text=answer, context=first["context"])
                self.assertEqual(status, 200)
                self.assert_route(turn, "4-001", "en", elevator=True)

    def test_voice_auto_and_explicit_languages(self):
        for preference, detected, transcript, expected, spoken_code in (
            ("auto", "english", "Room four oh five three. I use a wheelchair.", "en", "four, zero five three"),
            ("auto", "vi", "Phòng bốn không năm ba, tôi dùng xe lăn", "vi", "bốn, không năm ba"),
            ("en", "vi", "Room 4-053. I use a wheelchair.", "en", "four, zero five three"),
            ("vi", None, "Phòng 4-053, tôi dùng xe lăn", "vi", "bốn, không năm ba"),
            ("auto", None, "Where is room 4-053? I use a wheelchair.", "en", "four, zero five three"),
        ):
            with self.subTest(language=preference, transcript=transcript):
                mock_audio = b"ID3-mocked-mp3"
                self.openrouter.reset_mock()
                self.openrouter.side_effect = [
                    io.BytesIO(json.dumps({"text": transcript, "language": detected}).encode()),
                    io.BytesIO(mock_audio),
                ]
                status, result = self.submit("voice", language=preference, audio_base64=wav_fixture())
                self.assertEqual(status, 200)
                self.assertEqual(result["transcript"], transcript)
                self.assert_route(result, "4-053", expected, elevator=True)
                self.assertEqual((result["speech_status"], result["audio_media_type"]), ("ok", "audio/mpeg"))
                self.assertEqual(base64.b64decode(result["audio_base64"]), mock_audio)

                stt, tts = [call.args[0] for call in self.openrouter.call_args_list]
                self.assertTrue(stt.full_url.endswith("/audio/transcriptions"))
                self.assertTrue(tts.full_url.endswith("/audio/speech"))
                transcription_request, speech_request = json.loads(stt.data), json.loads(tts.data)
                self.assertEqual(transcription_request["input_audio"]["format"], "wav")
                if preference == "auto":
                    self.assertNotIn("language", transcription_request)
                    self.assertEqual(transcription_request["response_format"], "verbose_json")
                else:
                    self.assertEqual(transcription_request["language"], preference)
                self.assertEqual(speech_request["provider"]["options"]["elevenlabs"]["language_code"], expected)
                self.assertIn(spoken_code, speech_request["input"])

    def test_voice_misheard_name_then_appointment(self):
        # Giọng nói đi chung luồng: STT nghe sai → xác nhận → hỏi lịch hẹn → chỉ đường.
        self.openrouter.side_effect = [
            io.BytesIO(json.dumps({"text": text, "language": "vi"}).encode())
            for text in ("Tôi muốn làm điện tim đồ", "Đúng rồi", "Dạ rồi")
        ]
        audio = wav_fixture()
        status, turn = self.submit("voice", audio_base64=audio, speak=False)
        self.assertEqual((turn["status"], turn["context"]["pending"]), ("clarify", "confirm"))
        status, turn = self.submit("voice", audio_base64=audio, context=turn["context"], speak=False)
        self.assertEqual(turn["context"]["pending"], "appointment")
        status, turn = self.submit("voice", audio_base64=audio, context=turn["context"], speak=False)
        self.assert_route(turn, "3-009", "vi")

    def test_voice_uses_elevenlabs_when_its_key_is_set(self):
        mock_audio = b"ID3-mocked-mp3"
        with patch.object(settings, "ELEVENLABS_API_KEY", SecretStr("mock-eleven")), \
                patch("app.services.elevenlabs.urlopen") as eleven:
            eleven.side_effect = [
                io.BytesIO(json.dumps({"text": "Phòng 4-053, tôi dùng xe lăn", "language_code": "vie"}).encode()),
                io.BytesIO(mock_audio),
            ]
            status, result = self.submit("voice", audio_base64=wav_fixture())
        self.assertEqual(status, 200)
        self.assert_route(result, "4-053", "vi", elevator=True)
        self.assertEqual(base64.b64decode(result["audio_base64"]), mock_audio)
        self.openrouter.assert_not_called()

        stt, tts = [call.args[0] for call in eleven.call_args_list]
        self.assertTrue(stt.full_url.endswith("/v1/speech-to-text"))
        self.assertEqual(stt.get_header("Xi-api-key"), "mock-eleven")
        self.assertIn(b'name="model_id"', stt.data)
        self.assertIn(b'filename="speech.wav"', stt.data)
        self.assertIn(f"/v1/text-to-speech/{settings.ELEVENLABS_VOICE_ID}", tts.full_url)
        speech_request = json.loads(tts.data)
        self.assertEqual(speech_request["language_code"], "vi")
        self.assertIn("bốn, không năm ba", speech_request["text"])

    def fetch(self, path, method="GET"):
        request = Request(f"{self.base}/{path}", data=b"" if method == "POST" else None, method=method)
        try:
            with urlopen(request, timeout=10) as response:
                return response.status, response.headers, response.read()
        except HTTPError as error:
            with error:
                return error.code, error.headers, error.read()

    def test_realtime_session_mints_a_single_use_token(self):
        with patch.object(settings, "ELEVENLABS_API_KEY", SecretStr("mock-eleven")), \
                patch("app.services.elevenlabs.urlopen") as eleven:
            eleven.return_value = io.BytesIO(b'{"token": "sutkn_abc"}')
            status, headers, body = self.fetch("realtime?language=en", "POST")
        self.assertEqual(status, 200)
        self.assertEqual(headers["Cache-Control"], settings.WAYFINDING_CACHE_CONTROL)
        url = json.loads(body)["url"]
        self.assertTrue(url.startswith("wss://api.elevenlabs.io/v1/speech-to-text/realtime?"))
        for part in ("token=sutkn_abc", "language_code=en", "commit_strategy=vad", "audio_format=pcm_16000",
                     f"vad_silence_threshold_secs={settings.VOICE_END_SILENCE_SECS}"):
            self.assertIn(part, url)
        [request] = [call.args[0] for call in eleven.call_args_list]
        self.assertIn("/v1/single-use-token/realtime_scribe", request.full_url)
        self.assertEqual(request.get_header("Xi-api-key"), "mock-eleven")
        self.assertNotIn("mock-eleven", url)

        # Không có key ElevenLabs → 503 để kiosk lùi về bấm để nói; token lỗi → 502.
        status, _, body = self.fetch("realtime", "POST")
        self.assertEqual(status, settings.WAYFINDING_ERROR_STATUS["voice_not_configured"])
        with patch.object(settings, "ELEVENLABS_API_KEY", SecretStr("mock-eleven")), \
                patch("app.services.elevenlabs.urlopen") as eleven:
            eleven.side_effect = HTTPError("https://api.elevenlabs.io", 401, "Unauthorized", None, io.BytesIO())
            status, _, body = self.fetch("realtime", "POST")
        self.assertEqual(status, settings.WAYFINDING_ERROR_STATUS["transcription_failed"])
        self.openrouter.assert_not_called()

    def test_speech_streams_the_reply(self):
        text = quote("Để đến phòng 4-053, đi thẳng.")
        with patch.object(settings, "ELEVENLABS_API_KEY", SecretStr("mock-eleven")), \
                patch("app.services.elevenlabs.urlopen") as eleven:
            eleven.return_value = io.BytesIO(b"ID3" + bytes(40_000))
            status, headers, body = self.fetch(f"speech?language=vi&text={text}")
        self.assertEqual(status, 200)
        self.assertEqual(headers["Content-Type"], "audio/mpeg")
        self.assertEqual(body, b"ID3" + bytes(40_000))
        [request] = [call.args[0] for call in eleven.call_args_list]
        self.assertIn(f"/v1/text-to-speech/{settings.ELEVENLABS_VOICE_ID}/stream", request.full_url)
        self.assertIn("bốn, không năm ba", json.loads(request.data)["text"])
        self.assertIn("output_format=mp3_44100_128", request.full_url)

        with patch.object(settings, "ELEVENLABS_API_KEY", SecretStr("mock-eleven")),                 patch("app.services.elevenlabs.urlopen") as eleven:
            eleven.return_value = io.BytesIO(bytes(4_800))
            status, headers, body = self.fetch(f"speech?language=vi&format=pcm&text={text}")
        self.assertEqual((status, headers["Content-Type"], len(body)), (200, "audio/L16;rate=24000", 4_800))
        self.assertIn("output_format=pcm_24000", eleven.call_args.args[0].full_url)

        # Chỉ có OpenRouter: trả cả clip một lần.
        self.openrouter.side_effect = [io.BytesIO(b"ID3-openrouter")]
        status, _, body = self.fetch(f"speech?language=en&text={quote('Room 4-053')}")
        self.assertEqual((status, body), (200, b"ID3-openrouter"))
        status, _, _ = self.fetch(f"speech?format=pcm&text={text}")
        self.assertEqual(status, settings.WAYFINDING_ERROR_STATUS["speech_failed"])

        self.openrouter.side_effect = HTTPError("https://openrouter.ai", 503, "Unavailable", None, io.BytesIO())
        status, _, _ = self.fetch(f"speech?text={text}")
        self.assertEqual(status, settings.WAYFINDING_ERROR_STATUS["speech_failed"])
        status, _, _ = self.fetch("speech?text=")
        self.assertEqual(status, 422)
        with patch.object(settings, "OPENROUTER_API_KEY", None):
            status, _, _ = self.fetch(f"speech?text={text}")
        self.assertEqual(status, settings.WAYFINDING_ERROR_STATUS["voice_not_configured"])

    def test_english_route_survives_unavailable_speech(self):
        self.openrouter.side_effect = [
            io.BytesIO(b'{"text":"Room 4-053. I use a wheelchair."}'),
            HTTPError("https://openrouter.ai/api/v1/audio/speech", 503, "Unavailable", None, io.BytesIO()),
        ]
        status, result = self.submit("voice", language="en", audio_base64=wav_fixture())
        self.assertEqual(status, 200)
        self.assert_route(result, "4-053", "en", elevator=True)
        self.assertEqual(result["speech_status"], "unavailable")
        self.assertIsNone(result["audio_base64"])

    def test_service_errors_keep_the_http_contract(self):
        status, result = self.submit("text", kiosk_code="NO-SUCH-KIOSK", text="Room 4-053")
        self.assertEqual(status, settings.WAYFINDING_ERROR_STATUS["kiosk_not_found"])
        self.assertEqual(result, {"detail": "No active kiosk found."})

        status, result = self.submit("voice", language="en", audio_base64="invalid!")
        self.assertEqual(status, settings.WAYFINDING_ERROR_STATUS["invalid_audio"])
        self.assertEqual(result, {"detail": "Invalid base64 audio."})
        self.openrouter.assert_not_called()

        status, result = self.submit("voice", audio_base64=["submitted-audio"])
        self.assertEqual(status, 422)
        [error] = result["detail"]
        self.assertEqual(error["loc"], ["body", "audio_base64"])
        self.assertEqual(set(error), {"type", "loc", "msg"})

        with patch.object(settings, "OPENROUTER_API_KEY", None):
            status, result = self.submit("voice", language="en", audio_base64=wav_fixture())
            self.assertEqual(status, settings.WAYFINDING_ERROR_STATUS["voice_not_configured"])
            self.assertIn("Voice is not configured", result["detail"])

        self.openrouter.side_effect = HTTPError(
            "https://openrouter.ai/api/v1/audio/transcriptions",
            429, "Rate limit", None, io.BytesIO(),
        )
        status, result = self.submit("voice", language="en", audio_base64=wav_fixture())
        self.assertEqual(status, settings.WAYFINDING_ERROR_STATUS["transcription_failed"])
        self.assertIn("Speech recognition failed", result["detail"])

    def test_voice_clarification_in_both_languages(self):
        for language, question, answer in (
            ("en", "Where can I pay my bill? I use a wheelchair.", "On the fourth floor"),
            ("vi", "Tôi muốn đóng viện phí, tôi dùng xe lăn", "Ở tầng bốn"),
        ):
            with self.subTest(language=language):
                self.openrouter.side_effect = [
                    io.BytesIO(json.dumps({"text": text, "language": language}).encode())
                    for text in (question, answer)
                ]
                audio = wav_fixture()
                status, first = self.submit("voice", audio_base64=audio, speak=False)
                self.assertEqual(status, 200)
                self.assertEqual((first["status"], first["language"]), ("clarify", language))
                self.assertTrue(first["context"]["wheelchair"])
                status, result = self.submit(
                    "voice", audio_base64=audio, context=first["context"], speak=False,
                )
                self.assertEqual(status, 200)
                self.assertEqual(result["speech_status"], "skipped")
                self.assert_route(result, "4-001", language, elevator=True)


if __name__ == "__main__":
    unittest.main()
