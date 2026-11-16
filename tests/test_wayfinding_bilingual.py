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

    def test_text_departments_and_service_aliases(self):
        for utterance, code, language in (
            ("Where is the Cardiovascular Center?", "3-01", "en"),
            ("Chỉ đường đến Trung tâm Tim mạch", "3-01", "vi"),
            ("Where can I get an electrocardiogram?", "3-01-09", "en"),
            ("Tôi muốn đo điện tim", "3-01-09", "vi"),
        ):
            with self.subTest(utterance=utterance):
                status, result = self.submit("text", text=utterance)
                self.assertEqual(status, 200)
                self.assert_route(result, code, language)
        self.openrouter.assert_not_called()

    def test_english_clarification_keeps_language_and_accessibility(self):
        status, first = self.submit("text", text="Where can I pay my bill? I use a wheelchair.")
        self.assertEqual(status, 200)
        self.assertEqual((first["status"], first["language"]), ("clarify", "en"))
        self.assertTrue(first["context"]["wheelchair"])
        for answer in ("On the fourth floor, please", "On floor four", "4th floor"):
            with self.subTest(answer=answer):
                status, turn = self.submit("text", text=answer, context=first["context"])
                self.assertEqual(status, 200)
                self.assert_route(turn, "4-01-01", "en", elevator=True)

    def test_voice_auto_and_explicit_languages(self):
        for preference, detected, transcript, expected, spoken_code in (
            ("auto", "english", "Room four oh four eleven. I use a wheelchair.", "en", "four, zero four, one one"),
            ("auto", "vi", "Phòng bốn không bốn mười một, tôi dùng xe lăn", "vi", "bốn, không bốn, một một"),
            ("en", "vi", "Room 4-04-11. I use a wheelchair.", "en", "four, zero four, one one"),
            ("vi", None, "Phòng 4-04-11, tôi dùng xe lăn", "vi", "bốn, không bốn, một một"),
            ("auto", None, "Where is room 4-04-11? I use a wheelchair.", "en", "four, zero four, one one"),
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
                self.assert_route(result, "4-04-11", expected, elevator=True)
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

    def test_english_route_survives_unavailable_speech(self):
        self.openrouter.side_effect = [
            io.BytesIO(b'{"text":"Room 4-04-11. I use a wheelchair."}'),
            HTTPError("https://openrouter.ai/api/v1/audio/speech", 503, "Unavailable", None, io.BytesIO()),
        ]
        status, result = self.submit("voice", language="en", audio_base64=wav_fixture())
        self.assertEqual(status, 200)
        self.assert_route(result, "4-04-11", "en", elevator=True)
        self.assertEqual(result["speech_status"], "unavailable")
        self.assertIsNone(result["audio_base64"])

    def test_service_errors_keep_the_http_contract(self):
        status, result = self.submit("text", kiosk_code="NO-SUCH-KIOSK", text="Room 4-04-11")
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
            self.assertIn("OpenRouter is not configured", result["detail"])

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
                self.assert_route(result, "4-01-01", language, elevator=True)


if __name__ == "__main__":
    unittest.main()
