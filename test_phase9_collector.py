import os
import shutil
import tempfile
import json
import unittest
from datetime import datetime, timezone, timedelta

# 격리된 임시 APP_DATA_DIR
TEST_COLLECTOR_DIR = tempfile.mkdtemp(prefix="ai_bot_p9_collector_")
os.environ["APP_DATA_DIR"] = TEST_COLLECTOR_DIR

import core
import brain


class TestPhase9Collector(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        core._bootstrap_app_data_dir()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(TEST_COLLECTOR_DIR, ignore_errors=True)

    def test_01_heartbeat_cycle_and_observability(self):
        """수집기 Heartbeat 정상 기록 및 헬스 체크 관측 가능성 검증"""
        # 1. 사이클 완료 시 Heartbeat 기록
        brain._write_heartbeat(status="success", added=7)
        status = core.get_collector_status()

        self.assertIsNotNone(status)
        self.assertEqual(status.get("status"), "success")
        self.assertEqual(status.get("last_cycle_added"), 7)
        self.assertEqual(status.get("health"), "healthy")
        self.assertLess(status.get("age_seconds"), 5.0)
        print("  [PASSED] Test 01: Collector heartbeat recording & healthy state")

    def test_02_stale_heartbeat_detection(self):
        """오래된 Heartbeat 감지 시 health가 'stale'로 판별되는지 검증"""
        old_time = (datetime.now(timezone.utc) - timedelta(minutes=45)).isoformat()
        payload = {
            "status": "success",
            "updated_at": old_time,
            "last_cycle_added": 2,
        }
        with open(core.COLLECTOR_HEARTBEAT_PATH, "w", encoding="utf-8") as f:
            json.dump(payload, f)

        status = core.get_collector_status()
        self.assertEqual(status.get("health"), "stale")
        self.assertGreater(status.get("age_seconds"), 2000)
        print("  [PASSED] Test 02: Stale heartbeat (>30min) accurately flagged as 'stale'")


if __name__ == "__main__":
    unittest.main()
