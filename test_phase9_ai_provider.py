import os
import unittest
from unittest.mock import patch, MagicMock

import llm


class TestPhase9AIProvider(unittest.TestCase):
    def test_01_provider_configuration_and_secrets_redaction(self):
        """AI Provider 설정 및 비밀키 로깅 마스킹 검증"""
        self.assertTrue(llm.available())
        # Secret redaction test
        fake_secret = "AIzaSyD_TEST_SECRET_KEY_12345"
        llm._SECRETS.append(fake_secret)
        err = Exception(f"Failed with key {fake_secret} from api")
        brief = llm._brief(err)
        self.assertNotIn(fake_secret, brief)
        self.assertIn("[REDACTED]", brief)
        print("  [PASSED] Test 01: Provider configuration & secret redaction in exceptions")

    def test_02_scenario_a_primary_succeeds(self):
        """Scenario A: 1순위 Provider 성공 시 정상 스트리밍 검증"""
        def mock_primary():
            yield "Hello "
            yield "World!"

        with patch.dict(llm.__dict__, {"LLM_ORDER": ("gemini", "openai")}):
            with patch("llm._gemini_stream", return_value=mock_primary()):
                events = list(llm.generate_stream("test prompt"))
                # 첫 이벤트는 provider: gemini
                self.assertEqual(events[0], {"type": "provider", "provider": "gemini"})
                # 다음은 chunks
                chunks = [e["text"] for e in events if e["type"] == "chunk"]
                self.assertEqual("".join(chunks), "Hello World!")
        print("  [PASSED] Test 02: Scenario A (Primary provider succeeds)")

    def test_03_scenario_b_primary_fails_fallback_to_secondary(self):
        """Scenario B: 1순위 실패 시 2순위로 안전하게 전환(Failover) 검증"""
        def mock_fail():
            raise RuntimeError("Primary API quota exceeded (429)")

        def mock_secondary():
            yield "Fallback "
            yield "Success"

        with patch.dict(llm.__dict__, {"LLM_ORDER": ("gemini", "openai")}):
            with patch("llm._gemini_stream", side_effect=mock_fail):
                with patch("llm._openai_stream", return_value=mock_secondary()):
                    events = list(llm.generate_stream("test prompt"))
                    # 1순위 실패 후 2순위 openai로 전환
                    self.assertEqual(events[0], {"type": "provider", "provider": "openai"})
                    chunks = [e["text"] for e in events if e["type"] == "chunk"]
                    self.assertEqual("".join(chunks), "Fallback Success")
        print("  [PASSED] Test 03: Scenario B (Failover from primary to secondary before first chunk)")

    def test_04_scenario_c_all_providers_fail(self):
        """Scenario C: 모든 Provider 실패 시 크래시 없이 적절한 error 이벤트 반환 검증"""
        def mock_fail():
            raise RuntimeError("Network timeout")

        with patch.dict(llm.__dict__, {"LLM_ORDER": ("gemini", "openai")}):
            with patch("llm._gemini_stream", side_effect=mock_fail):
                with patch("llm._openai_stream", side_effect=mock_fail):
                    events = list(llm.generate_stream("test prompt"))
                    self.assertEqual(len(events), 1)
                    self.assertEqual(events[0]["type"], "error")
                    self.assertIn("gemini", events[0]["message"])
                    self.assertIn("openai", events[0]["message"])
        print("  [PASSED] Test 04: Scenario C (All providers fail -> clean error event without infinite loop)")

    def test_05_scenario_d_streaming_midway_failure(self):
        """Scenario D: 스트리밍 도중 오류 발생 시 답변 혼합 방지 및 중단 에러 반환 검증"""
        def mock_midway_fail():
            yield "Starting response..."
            raise ConnectionResetError("Connection lost mid-stream")

        with patch.dict(llm.__dict__, {"LLM_ORDER": ("gemini", "openai")}):
            with patch("llm._gemini_stream", return_value=mock_midway_fail()):
                events = list(llm.generate_stream("test prompt"))
                # Provider 이벤트 발생
                self.assertEqual(events[0], {"type": "provider", "provider": "gemini"})
                # 첫 조각 수신
                self.assertEqual(events[1], {"type": "chunk", "text": "Starting response..."})
                # 도중 오류 발생 시 다른 provider로 전환되지 않고 error 반환
                self.assertEqual(events[2], {"type": "error", "message": "답변 전송이 중단되었습니다."})
        print("  [PASSED] Test 05: Scenario D (Midway streaming failure prevents chimeric mixed responses)")


if __name__ == "__main__":
    unittest.main()
