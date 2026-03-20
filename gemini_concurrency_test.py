"""
Gemini API Concurrency Tester
=============================
Tests concurrent connections to the Gemini API, measuring response times,
success/failure rates, and throughput under load.

Usage:
    python gemini_concurrency_test.py --sessions 5 --prompts-per-session 3 --model gemini-2.0-flash

Results are saved to gemini_test_results.json for the Streamlit dashboard.
"""

import argparse
import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import List, Optional

from dotenv import load_dotenv
import google.generativeai as genai

load_dotenv()

# ── Logging setup ──────────────────────────────────────────────────────────────

LOG_FILE = "gemini_concurrency_test.log"
RESULTS_FILE = "gemini_test_results.json"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, mode="w", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("gemini_concurrency")

# ── Data classes ───────────────────────────────────────────────────────────────

@dataclass
class RequestResult:
    session_id: int
    prompt_index: int
    prompt: str
    response_preview: str  # first 200 chars of the response
    status: str  # "success" or "error"
    error_message: Optional[str]
    start_time: float
    end_time: float
    latency_seconds: float


@dataclass
class SessionResult:
    session_id: int
    total_prompts: int
    successful: int
    failed: int
    start_time: float
    end_time: float
    total_duration_seconds: float
    requests: List[RequestResult] = field(default_factory=list)


@dataclass
class TestRun:
    run_id: str
    model: str
    concurrent_sessions: int
    prompts_per_session: int
    prompts_used: List[str]
    start_time: float
    end_time: float
    total_duration_seconds: float
    sessions: List[SessionResult] = field(default_factory=list)


# ── Default prompts ────────────────────────────────────────────────────────────

DEFAULT_PROMPTS = [
    "Explain the concept of recursion in programming in 2 sentences.",
    "What is the time complexity of binary search? Answer briefly.",
    "Give me a short Python function to reverse a string.",
    "What are the SOLID principles? List them in one line each.",
    "Explain the difference between a stack and a queue in 2 sentences.",
    "What is Big-O notation? Answer in 3 sentences max.",
    "Write a one-liner Python list comprehension that squares all even numbers from 1 to 20.",
    "What is a hash table? Explain in 2 sentences.",
    "Describe the observer design pattern in 2 sentences.",
    "What is the difference between concurrency and parallelism? Brief answer.",
]


# ── Core logic ─────────────────────────────────────────────────────────────────

async def run_single_request(
    model: genai.GenerativeModel,
    session_id: int,
    prompt_index: int,
    prompt: str,
) -> RequestResult:
    """Send a single prompt to Gemini and record timing + result."""
    logger.info(
        "Session %d | Prompt %d | SENDING: %s", session_id, prompt_index, prompt[:80]
    )
    start = time.perf_counter()
    try:
        response = await asyncio.to_thread(model.generate_content, prompt)
        end = time.perf_counter()
        text = response.text[:200] if response.text else "(empty)"
        logger.info(
            "Session %d | Prompt %d | SUCCESS | %.3fs | Response: %s",
            session_id, prompt_index, end - start, text[:80],
        )
        return RequestResult(
            session_id=session_id,
            prompt_index=prompt_index,
            prompt=prompt,
            response_preview=text,
            status="success",
            error_message=None,
            start_time=start,
            end_time=end,
            latency_seconds=round(end - start, 4),
        )
    except Exception as exc:
        end = time.perf_counter()
        logger.error(
            "Session %d | Prompt %d | ERROR | %.3fs | %s",
            session_id, prompt_index, end - start, exc,
        )
        return RequestResult(
            session_id=session_id,
            prompt_index=prompt_index,
            prompt=prompt,
            response_preview="",
            status="error",
            error_message=str(exc),
            start_time=start,
            end_time=end,
            latency_seconds=round(end - start, 4),
        )


async def run_session(
    model: genai.GenerativeModel,
    session_id: int,
    prompts: List[str],
) -> SessionResult:
    """Run one session that sequentially sends all prompts."""
    logger.info("Session %d | STARTED with %d prompts", session_id, len(prompts))
    session_start = time.perf_counter()
    requests: List[RequestResult] = []

    for idx, prompt in enumerate(prompts):
        result = await run_single_request(model, session_id, idx, prompt)
        requests.append(result)

    session_end = time.perf_counter()
    successful = sum(1 for r in requests if r.status == "success")
    failed = len(requests) - successful
    duration = round(session_end - session_start, 4)

    logger.info(
        "Session %d | FINISHED | %.3fs | %d/%d succeeded",
        session_id, duration, successful, len(requests),
    )
    return SessionResult(
        session_id=session_id,
        total_prompts=len(prompts),
        successful=successful,
        failed=failed,
        start_time=session_start,
        end_time=session_end,
        total_duration_seconds=duration,
        requests=requests,
    )


async def run_test(
    api_key: str,
    model_name: str,
    num_sessions: int,
    prompts_per_session: int,
    custom_prompts: Optional[List[str]] = None,
) -> TestRun:
    """Launch *num_sessions* concurrent sessions, each sending prompts."""
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(model_name)

    # Build prompt list for each session (cycle through available prompts)
    all_prompts: List[str] = custom_prompts or DEFAULT_PROMPTS
    session_prompts = [
        [all_prompts[j % len(all_prompts)] for j in range(prompts_per_session)]
        for _ in range(num_sessions)
    ]

    logger.info("=" * 70)
    logger.info(
        "TEST START | Model: %s | Sessions: %d | Prompts/session: %d",
        model_name, num_sessions, prompts_per_session,
    )
    logger.info("=" * 70)

    test_start = time.perf_counter()

    tasks = [
        run_session(model, sid, session_prompts[sid])
        for sid in range(num_sessions)
    ]
    sessions = await asyncio.gather(*tasks)

    test_end = time.perf_counter()
    duration = round(test_end - test_start, 4)

    logger.info("=" * 70)
    logger.info("TEST COMPLETE | Total time: %.3fs", duration)
    logger.info("=" * 70)

    run_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return TestRun(
        run_id=run_id,
        model=model_name,
        concurrent_sessions=num_sessions,
        prompts_per_session=prompts_per_session,
        prompts_used=all_prompts[:prompts_per_session],
        start_time=test_start,
        end_time=test_end,
        total_duration_seconds=duration,
        sessions=list(sessions),
    )


def save_results(test_run: TestRun, path: str = RESULTS_FILE) -> None:
    """Append the test run to results JSON (keeps history of runs)."""
    existing: List[dict] = []
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            try:
                existing = json.load(f)
            except json.JSONDecodeError:
                existing = []
    existing.append(asdict(test_run))
    with open(path, "w", encoding="utf-8") as f:
        json.dump(existing, f, indent=2)
    logger.info("Results saved to %s", path)


# ── CLI entry point ───────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Gemini API Concurrency Tester",
    )
    parser.add_argument(
        "--sessions", "-s", type=int, default=5,
        help="Number of concurrent sessions (default: 5)",
    )
    parser.add_argument(
        "--prompts-per-session", "-p", type=int, default=3,
        help="Number of prompts each session sends (default: 3)",
    )
    parser.add_argument(
        "--model", "-m", type=str, default="gemini-2.0-flash",
        help="Gemini model name (default: gemini-2.0-flash)",
    )
    parser.add_argument(
        "--api-key", type=str, default=None,
        help="Gemini API key (or set GEMINI_API_KEY env var)",
    )
    args = parser.parse_args()

    api_key = args.api_key or os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        logger.error("No API key provided. Use --api-key or set GEMINI_API_KEY env var.")
        raise SystemExit(1)

    test_run = asyncio.run(
        run_test(
            api_key=api_key,
            model_name=args.model,
            num_sessions=args.sessions,
            prompts_per_session=args.prompts_per_session,
        )
    )
    save_results(test_run)

    # Quick summary
    total_req = sum(s.total_prompts for s in test_run.sessions)
    total_ok = sum(s.successful for s in test_run.sessions)
    total_fail = sum(s.failed for s in test_run.sessions)
    latencies = [r.latency_seconds for s in test_run.sessions for r in s.requests if r.status == "success"]
    avg_lat = sum(latencies) / len(latencies) if latencies else 0

    print("\n" + "=" * 50)
    print(f"  Total requests : {total_req}")
    print(f"  Successful     : {total_ok}")
    print(f"  Failed         : {total_fail}")
    print(f"  Avg latency    : {avg_lat:.3f}s")
    print(f"  Total time     : {test_run.total_duration_seconds:.3f}s")
    print(f"  Throughput     : {total_req / test_run.total_duration_seconds:.2f} req/s")
    print("=" * 50)


if __name__ == "__main__":
    main()
