import os
import sys
import subprocess
import time

TEST_SUITES = [
    ("Phase 1~7 Core Regression", "test_phase1_to_7_regression.py"),
    ("Phase 8 Generation Resilience & Crash", "test_phase8_resilience.py"),
    ("Phase 9 Backend Runtime & Probes", "test_phase9_backend_runtime.py"),
    ("Phase 9 AI Provider & Failover", "test_phase9_ai_provider.py"),
    ("Phase 9 Security Audit & Injection", "test_phase9_security_audit.py"),
    ("Phase 9 Collector & Heartbeat", "test_phase9_collector.py"),
    ("Phase 9 RAG Retrieval & Citations", "test_phase9_rag_citations.py"),
    ("Phase 9 Upload & Storage Simulation", "test_phase9_upload_storage.py"),
    ("Phase 9 Real Browser Playwright E2E", "test_phase9_browser_e2e.py"),
]

def main():
    print("=" * 70)
    print("🧪 [PHASE 9] Master Acceptance & Release QA Test Runner")
    print("=" * 70)

    results = []
    overall_start = time.perf_counter()

    for name, script in TEST_SUITES:
        print(f"\n▶ Running: {name} ({script})...")
        t0 = time.perf_counter()
        proc = subprocess.run(
            [sys.executable, script],
            capture_output=True,
            text=True
        )
        duration = time.perf_counter() - t0
        passed = proc.returncode == 0
        status = "PASS" if passed else "FAIL"
        results.append((name, script, status, duration, proc.stdout, proc.stderr))

        if passed:
            print(f"  ✅ {name}: PASS ({duration:.2f}s)")
        else:
            print(f"  ❌ {name}: FAIL ({duration:.2f}s)")
            print("--- STDOUT ---")
            print(proc.stdout[-500:] if len(proc.stdout) > 500 else proc.stdout)
            print("--- STDERR ---")
            print(proc.stderr[-500:] if len(proc.stderr) > 500 else proc.stderr)

    total_duration = time.perf_counter() - overall_start

    print("\n" + "=" * 70)
    print("📊 FINAL ACCEPTANCE TEST SUMMARY")
    print("=" * 70)
    print(f"{'Test Suite':<40} | {'Status':<8} | {'Duration'}")
    print("-" * 70)

    all_passed = True
    for name, script, status, dur, _, _ in results:
        print(f"{name:<40} | {status:<8} | {dur:.2f}s")
        if status != "PASS":
            all_passed = False

    print("-" * 70)
    print(f"Total Execution Time: {total_duration:.2f}s")
    print(f"Overall Result: {'ALL SUITES PASSED' if all_passed else 'SOME SUITES FAILED'}")
    print("=" * 70)

    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
