"""
Simli + LiveKit Concurrency Tester
===================================
Tests concurrent Simli avatar session creation by:
  1. Generating a LiveKit access token (local, via livekit-api SDK)
  2. Calling Simli /compose/token to create a session token
  3. Calling Simli /integrations/livekit/agents to start the avatar agent

Focuses on the two Simli API endpoints — measures latency, success/failure,
and throughput under concurrent load.

Results are saved to simli_test_results.json for the Streamlit dashboard.

Usage:
    python simli_concurrency_test.py --sessions 5
"""

import argparse
import asyncio
import json
import logging
import os
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import List, Optional

import aiohttp
from dotenv import load_dotenv
from livekit import api as lk_api

load_dotenv()

# ── Logging ────────────────────────────────────────────────────────────────────

LOG_FILE = "simli_concurrency_test.log"
RESULTS_FILE = "simli_test_results.json"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, mode="w", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("simli_concurrency")

# ── Data classes ───────────────────────────────────────────────────────────────


@dataclass
class StepLog:
    step: str
    status: str  # "success" | "error"
    start_time: float
    end_time: float
    latency_seconds: float
    detail: str
    error_message: Optional[str] = None


@dataclass
class SessionResult:
    session_id: int
    room_name: str
    steps: List[StepLog] = field(default_factory=list)
    total_duration_seconds: float = 0.0
    status: str = "pending"  # "success" | "error"
    session_token_created: bool = False
    agent_started: bool = False


@dataclass
class TestRun:
    run_id: str
    concurrent_sessions: int
    start_time: float
    end_time: float
    total_duration_seconds: float
    total_session_tokens_created: int
    total_agents_started: int
    sessions: List[SessionResult] = field(default_factory=list)


# ── Helpers ────────────────────────────────────────────────────────────────────


def _generate_livekit_token(
    api_key: str, api_secret: str, room_name: str, identity: str
) -> str:
    """Generate a LiveKit access token using the Python SDK."""
    token = (
        lk_api.AccessToken(api_key, api_secret)
        .with_identity(identity)
        .with_name(identity)
        .with_grants(
            lk_api.VideoGrants(
                room_join=True,
                room=room_name,
                can_publish=True,
                can_subscribe=True,
            )
        )
    )
    return token.to_jwt()


async def _create_simli_session_token(
    http: aiohttp.ClientSession,
    simli_api_key: str,
    face_id: str,
) -> str:
    """POST /compose/token → returns a session_token."""
    url = "https://api.simli.ai/compose/token"
    payload = {
        "faceId": face_id,
        "apiVersion": "v2",
        "handleSilence": True,
        "maxSessionLength": 3600,
        "maxIdleTime": 300,
        "startFrame": 0,
        "audioInputFormat": "pcm16",
    }
    headers = {
        "Content-Type": "application/json",
        "x-simli-api-key": simli_api_key,
    }
    async with http.post(url, json=payload, headers=headers) as resp:
        body = await resp.text()
        resp.raise_for_status()
        data = json.loads(body)
        return data["session_token"]


async def _start_simli_livekit_agent(
    http: aiohttp.ClientSession,
    session_token: str,
    livekit_token: str,
    livekit_url: str,
) -> dict:
    """POST /integrations/livekit/agents → starts simli avatar agent."""
    url = "https://api.simli.ai/integrations/livekit/agents"
    payload = {
        "session_token": session_token,
        "livekit_token": livekit_token,
        "livekit_url": livekit_url,
    }
    headers = {"Content-Type": "application/json"}
    async with http.post(url, json=payload, headers=headers) as resp:
        body = await resp.text()
        resp.raise_for_status()
        return json.loads(body)


# ── Single session ─────────────────────────────────────────────────────────────


async def run_single_session(
    session_id: int,
    simli_api_key: str,
    face_id: str,
    lk_api_key: str,
    lk_api_secret: str,
    lk_url: str,
) -> SessionResult:
    room_name = f"simli-test-{uuid.uuid4().hex[:8]}"
    identity = f"tester-{session_id}"
    result = SessionResult(session_id=session_id, room_name=room_name)
    session_start = time.perf_counter()

    # Step 1 – Generate LiveKit token (local, fast)
    step_start = time.perf_counter()
    try:
        lk_token = _generate_livekit_token(lk_api_key, lk_api_secret, room_name, identity)
        step_end = time.perf_counter()
        logger.info("Session %d | Step 1 | LiveKit token generated | %.3fs", session_id, step_end - step_start)
        result.steps.append(StepLog(
            step="generate_livekit_token", status="success",
            start_time=step_start, end_time=step_end,
            latency_seconds=round(step_end - step_start, 4),
            detail=f"room={room_name} identity={identity}",
        ))
    except Exception as exc:
        step_end = time.perf_counter()
        logger.error("Session %d | Step 1 | LiveKit token FAILED | %s", session_id, exc)
        result.steps.append(StepLog(
            step="generate_livekit_token", status="error",
            start_time=step_start, end_time=step_end,
            latency_seconds=round(step_end - step_start, 4),
            detail="", error_message=str(exc),
        ))
        result.status = "error"
        result.total_duration_seconds = round(step_end - session_start, 4)
        return result

    async with aiohttp.ClientSession() as http:
        # Step 2 – Create Simli session token  (/compose/token)
        step_start = time.perf_counter()
        try:
            simli_token = await _create_simli_session_token(http, simli_api_key, face_id)
            step_end = time.perf_counter()
            result.session_token_created = True
            logger.info("Session %d | Step 2 | Simli session token created | %.3fs", session_id, step_end - step_start)
            result.steps.append(StepLog(
                step="create_simli_session_token", status="success",
                start_time=step_start, end_time=step_end,
                latency_seconds=round(step_end - step_start, 4),
                detail=f"token_preview={simli_token[:30]}...",
            ))
        except Exception as exc:
            step_end = time.perf_counter()
            logger.error("Session %d | Step 2 | Simli session token FAILED | %s", session_id, exc)
            result.steps.append(StepLog(
                step="create_simli_session_token", status="error",
                start_time=step_start, end_time=step_end,
                latency_seconds=round(step_end - step_start, 4),
                detail="", error_message=str(exc),
            ))
            result.status = "error"
            result.total_duration_seconds = round(step_end - session_start, 4)
            return result

        # Step 3 – Start Simli LiveKit agent  (/integrations/livekit/agents)
        step_start = time.perf_counter()
        try:
            agent_resp = await _start_simli_livekit_agent(http, simli_token, lk_token, lk_url)
            step_end = time.perf_counter()
            result.agent_started = True
            logger.info(
                "Session %d | Step 3 | Simli agent started | %.3fs | response=%s",
                session_id, step_end - step_start, json.dumps(agent_resp)[:200],
            )
            result.steps.append(StepLog(
                step="start_simli_livekit_agent", status="success",
                start_time=step_start, end_time=step_end,
                latency_seconds=round(step_end - step_start, 4),
                detail=json.dumps(agent_resp)[:200],
            ))
        except Exception as exc:
            step_end = time.perf_counter()
            logger.error("Session %d | Step 3 | Simli agent start FAILED | %s", session_id, exc)
            result.steps.append(StepLog(
                step="start_simli_livekit_agent", status="error",
                start_time=step_start, end_time=step_end,
                latency_seconds=round(step_end - step_start, 4),
                detail="", error_message=str(exc),
            ))
            result.status = "error"
            result.total_duration_seconds = round(step_end - session_start, 4)
            return result

    session_end = time.perf_counter()
    result.total_duration_seconds = round(session_end - session_start, 4)
    result.status = "success"
    logger.info(
        "Session %d | FINISHED | %.3fs | token=%s agent=%s",
        session_id, result.total_duration_seconds,
        result.session_token_created, result.agent_started,
    )
    return result


# ── Room cleanup ───────────────────────────────────────────────────────────────


async def _cleanup_rooms(
    lk_url: str, lk_api_key: str, lk_api_secret: str, room_names: List[str]
) -> None:
    """Delete LiveKit rooms that were created during the test."""
    from livekit.protocol.room import DeleteRoomRequest

    logger.info("Cleaning up %d test rooms …", len(room_names))
    lk = lk_api.LiveKitAPI(lk_url, lk_api_key, lk_api_secret)
    try:
        for name in room_names:
            try:
                await lk.room.delete_room(DeleteRoomRequest(room=name))
                logger.info("Deleted room: %s", name)
            except Exception as exc:
                logger.warning("Could not delete room %s: %s", name, exc)
    finally:
        await lk.aclose()
    logger.info("Room cleanup complete.")


# ── Test runner ────────────────────────────────────────────────────────────────


async def run_simli_test(
    simli_api_key: str,
    face_id: str,
    lk_api_key: str,
    lk_api_secret: str,
    lk_url: str,
    num_sessions: int,
    interval_seconds: float = 0.0,
) -> TestRun:
    logger.info("=" * 70)
    logger.info("SIMLI TEST START | Sessions: %d | Interval: %.2fs", num_sessions, interval_seconds)
    logger.info("=" * 70)

    test_start = time.perf_counter()

    tasks: List[asyncio.Task] = []
    for sid in range(num_sessions):
        task = asyncio.create_task(
            run_single_session(
                session_id=sid,
                simli_api_key=simli_api_key,
                face_id=face_id,
                lk_api_key=lk_api_key,
                lk_api_secret=lk_api_secret,
                lk_url=lk_url,
            )
        )
        tasks.append(task)
        if interval_seconds > 0 and sid < num_sessions - 1:
            await asyncio.sleep(interval_seconds)
    sessions = await asyncio.gather(*tasks)

    test_end = time.perf_counter()
    duration = round(test_end - test_start, 4)
    total_tokens = sum(1 for s in sessions if s.session_token_created)
    total_agents = sum(1 for s in sessions if s.agent_started)

    logger.info("=" * 70)
    logger.info(
        "SIMLI TEST COMPLETE | %.3fs | tokens=%d/%d agents=%d/%d",
        duration, total_tokens, num_sessions, total_agents, num_sessions,
    )
    logger.info("=" * 70)

    # ── Cleanup: delete rooms created during the test ──────────────────────
    room_names = [s.room_name for s in sessions]
    await _cleanup_rooms(lk_url, lk_api_key, lk_api_secret, room_names)

    run_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return TestRun(
        run_id=run_id,
        concurrent_sessions=num_sessions,
        start_time=test_start,
        end_time=test_end,
        total_duration_seconds=duration,
        total_session_tokens_created=total_tokens,
        total_agents_started=total_agents,
        sessions=list(sessions),
    )


def save_simli_results(test_run: TestRun, path: str = RESULTS_FILE) -> None:
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


# ── CLI ────────────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(description="Simli + LiveKit Concurrency Tester")
    parser.add_argument("--sessions", "-s", type=int, default=3, help="Concurrent sessions (default: 3)")
    args = parser.parse_args()

    simli_api_key = os.environ.get("SIMLI_API_KEY", "")
    face_id = os.environ.get("FACE_ID", "")
    lk_api_key = os.environ.get("LIVEKIT_API_KEY", "")
    lk_api_secret = os.environ.get("LIVEKIT_API_SECRET", "")
    lk_url = os.environ.get("LIVEKIT_URL", "")

    missing = []
    if not simli_api_key:
        missing.append("SIMLI_API_KEY")
    if not face_id:
        missing.append("FACE_ID")
    if not lk_api_key:
        missing.append("LIVEKIT_API_KEY")
    if not lk_api_secret:
        missing.append("LIVEKIT_API_SECRET")
    if not lk_url:
        missing.append("LIVEKIT_URL")
    if missing:
        logger.error("Missing env vars: %s", ", ".join(missing))
        raise SystemExit(1)

    test_run = asyncio.run(
        run_simli_test(
            simli_api_key=simli_api_key,
            face_id=face_id,
            lk_api_key=lk_api_key,
            lk_api_secret=lk_api_secret,
            lk_url=lk_url,
            num_sessions=args.sessions,
        )
    )
    save_simli_results(test_run)

    total = len(test_run.sessions)
    ok_tokens = test_run.total_session_tokens_created
    ok_agents = test_run.total_agents_started

    print("\n" + "=" * 50)
    print(f"  Total sessions          : {total}")
    print(f"  Session tokens created  : {ok_tokens}/{total}")
    print(f"  Agents started          : {ok_agents}/{total}")
    print(f"  Total time              : {test_run.total_duration_seconds:.3f}s")
    print("=" * 50)


if __name__ == "__main__":
    main()
