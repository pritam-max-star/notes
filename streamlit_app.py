"""
Concurrency Test Dashboard
============================
Streamlit app with two tabs:
  1. Gemini API concurrency tester
  2. Simli + LiveKit avatar concurrency tester

Run:  streamlit run streamlit_app.py
"""

import asyncio
import json
import os
import time

from dotenv import load_dotenv
load_dotenv()

import matplotlib
matplotlib.use("Agg")                       # non-interactive backend for Streamlit
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import numpy as np
import streamlit as st

from gemini_concurrency_test import (
    RESULTS_FILE as GEMINI_RESULTS_FILE,
    LOG_FILE as GEMINI_LOG_FILE,
    run_test as gemini_run_test,
    save_results as gemini_save_results,
)
from simli_concurrency_test import (
    RESULTS_FILE as SIMLI_RESULTS_FILE,
    LOG_FILE as SIMLI_LOG_FILE,
    run_simli_test,
    save_simli_results,
)
from dataclasses import asdict

# ── Page config ────────────────────────────────────────────────────────────────

st.set_page_config(page_title="Concurrency Tester", layout="wide")
st.title("⚡ Concurrency Test Dashboard")


def show_fig(fig):
    st.pyplot(fig, use_container_width=True)
    plt.close(fig)


def _load_json(path):
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return []


# ── Tabs ───────────────────────────────────────────────────────────────────────

tab_gemini, tab_simli = st.tabs(["Gemini API Test", "Simli + LiveKit Test"])

# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  TAB 1 – GEMINI                                                             ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

with tab_gemini:

    # ── Sidebar-like config inside tab ─────────────────────────────────────────
    with st.expander("Gemini Test Configuration", expanded=False):
        gc1, gc2, gc3, gc4 = st.columns(4)
        api_key = gc1.text_input(
            "Gemini API Key",
            value=os.environ.get("GEMINI_API_KEY", ""),
            type="password",
            key="gemini_api_key",
        )
        model_name = gc2.text_input("Model name", value="gemini-2.0-flash", key="gemini_model")
        num_sessions = gc3.slider("Concurrent sessions", 1, 500, 5, key="gemini_sessions")
        prompts_per_session = gc4.slider("Prompts / session", 1, 20, 3, key="gemini_prompts")
        run_gemini = st.button("🚀 Run Gemini Test", key="run_gemini", use_container_width=True)

    if run_gemini:
        if not api_key:
            st.error("Please provide a Gemini API key.")
        else:
            with st.spinner(f"Running {num_sessions} sessions × {prompts_per_session} prompts …"):
                test_run = asyncio.run(
                    gemini_run_test(
                        api_key=api_key,
                        model_name=model_name,
                        num_sessions=num_sessions,
                        prompts_per_session=prompts_per_session,
                    )
                )
                gemini_save_results(test_run)
            st.success(f"Test **{test_run.run_id}** completed!")
            st.rerun()

    results = _load_json(GEMINI_RESULTS_FILE)

    if not results:
        st.info("No Gemini test results yet. Run a test above.")
    else:
        run_ids = [r["run_id"] for r in results]
        selected_run_id = st.selectbox(
            "Select Gemini test run",
            options=run_ids[::-1],
            format_func=lambda rid: f"Run {rid} – {next(r['concurrent_sessions'] for r in results if r['run_id'] == rid)} sessions",
            key="gemini_run_select",
        )
        run_data = next(r for r in results if r["run_id"] == selected_run_id)

        all_requests = [req for s in run_data["sessions"] for req in s["requests"]]
        success_requests = [r for r in all_requests if r["status"] == "success"]
        error_requests = [r for r in all_requests if r["status"] == "error"]
        latencies = [r["latency_seconds"] for r in success_requests]

        total_reqs = len(all_requests)
        throughput = total_reqs / run_data["total_duration_seconds"] if run_data["total_duration_seconds"] else 0
        avg_latency = np.mean(latencies) if latencies else 0
        p50 = np.percentile(latencies, 50) if latencies else 0
        p95 = np.percentile(latencies, 95) if latencies else 0
        p99 = np.percentile(latencies, 99) if latencies else 0

        k1, k2, k3, k4, k5, k6 = st.columns(6)
        k1.metric("Total Requests", total_reqs)
        k2.metric("Successful", len(success_requests))
        k3.metric("Failed", len(error_requests))
        k4.metric("Avg Latency (s)", f"{avg_latency:.3f}")
        k5.metric("Throughput (req/s)", f"{throughput:.2f}")
        k6.metric("Total Time (s)", f"{run_data['total_duration_seconds']:.2f}")

        st.divider()

        # Chart 1: Latency distribution histogram
        st.subheader("1 · Latency Distribution")
        col_a, col_b = st.columns(2)
        with col_a:
            fig1, ax1 = plt.subplots(figsize=(7, 4))
            if latencies:
                ax1.hist(latencies, bins=max(10, len(latencies) // 3), color="#4A90D9", edgecolor="white", alpha=0.85)
                ax1.axvline(avg_latency, color="red", linestyle="--", linewidth=1.5, label=f"Mean = {avg_latency:.3f}s")
                ax1.axvline(p95, color="orange", linestyle="--", linewidth=1.5, label=f"P95 = {p95:.3f}s")
                ax1.legend()
            ax1.set_xlabel("Latency (seconds)")
            ax1.set_ylabel("Count")
            ax1.set_title("Response Latency Distribution")
            fig1.tight_layout()
            show_fig(fig1)

        with col_b:
            fig2, ax2 = plt.subplots(figsize=(7, 4))
            session_latencies = []
            session_labels = []
            for s in run_data["sessions"]:
                lats = [r["latency_seconds"] for r in s["requests"] if r["status"] == "success"]
                if lats:
                    session_latencies.append(lats)
                    session_labels.append(f"S{s['session_id']}")
            if session_latencies:
                bp = ax2.boxplot(session_latencies, labels=session_labels, patch_artist=True)
                colors = plt.cm.tab10(np.linspace(0, 1, len(session_latencies)))
                for patch, color in zip(bp["boxes"], colors):
                    patch.set_facecolor(color)
            ax2.set_xlabel("Session")
            ax2.set_ylabel("Latency (seconds)")
            ax2.set_title("Latency Box Plot per Session")
            fig2.tight_layout()
            show_fig(fig2)

        # Chart 3: Timeline
        st.subheader("2 · Request Timeline")
        fig3, ax3 = plt.subplots(figsize=(14, min(40, max(4, len(all_requests) * 0.22))))
        base_time = run_data["start_time"]
        colors_map = {"success": "#27AE60", "error": "#E74C3C"}
        for i, req in enumerate(sorted(all_requests, key=lambda r: (r["session_id"], r["prompt_index"]))):
            start_rel = req["start_time"] - base_time
            duration = req["latency_seconds"]
            color = colors_map.get(req["status"], "gray")
            ax3.barh(i, duration, left=start_rel, height=0.7, color=color, edgecolor="white", linewidth=0.3)
        ax3.set_xlabel("Time since test start (seconds)")
        ax3.set_ylabel("Request #")
        ax3.set_title("Request Timeline (green = success, red = error)")
        ax3.invert_yaxis()
        fig3.tight_layout()
        show_fig(fig3)

        # Charts 4-5: Throughput + Success/Failure
        st.subheader("3 · Throughput Over Time")
        col_c, col_d = st.columns(2)
        with col_c:
            fig4, ax4 = plt.subplots(figsize=(7, 4))
            if all_requests:
                end_times_rel = [r["end_time"] - base_time for r in all_requests]
                max_t = max(end_times_rel)
                bucket_size = max(0.5, max_t / 30)
                bins = np.arange(0, max_t + bucket_size, bucket_size)
                counts, edges = np.histogram(end_times_rel, bins=bins)
                throughputs_arr = counts / bucket_size
                ax4.bar(edges[:-1], throughputs_arr, width=bucket_size * 0.9, color="#8E44AD", alpha=0.8, align="edge")
            ax4.set_xlabel("Time (seconds)")
            ax4.set_ylabel("Requests / second")
            ax4.set_title("Throughput Over Time")
            fig4.tight_layout()
            show_fig(fig4)

        with col_d:
            fig5, ax5 = plt.subplots(figsize=(7, 4))
            sessions_ids = [f"S{s['session_id']}" for s in run_data["sessions"]]
            successes = [s["successful"] for s in run_data["sessions"]]
            failures = [s["failed"] for s in run_data["sessions"]]
            x = np.arange(len(sessions_ids))
            width = 0.35
            ax5.bar(x - width / 2, successes, width, label="Success", color="#27AE60")
            ax5.bar(x + width / 2, failures, width, label="Failed", color="#E74C3C")
            ax5.set_xticks(x)
            ax5.set_xticklabels(sessions_ids)
            ax5.yaxis.set_major_locator(ticker.MaxNLocator(integer=True))
            ax5.set_xlabel("Session")
            ax5.set_ylabel("Requests")
            ax5.set_title("Success vs Failure per Session")
            ax5.legend()
            fig5.tight_layout()
            show_fig(fig5)

        # Charts 6-7: Session durations + Latency by prompt
        st.subheader("4 · Session Durations")
        col_e, col_f = st.columns(2)
        with col_e:
            fig6, ax6 = plt.subplots(figsize=(7, 4))
            durations = [s["total_duration_seconds"] for s in run_data["sessions"]]
            colors6 = plt.cm.viridis(np.linspace(0.2, 0.8, len(durations)))
            ax6.bar(sessions_ids, durations, color=colors6)
            ax6.set_xlabel("Session")
            ax6.set_ylabel("Duration (seconds)")
            ax6.set_title("Total Duration per Session")
            fig6.tight_layout()
            show_fig(fig6)

        with col_f:
            fig7, ax7 = plt.subplots(figsize=(7, 4))
            prompt_indices = sorted(set(r["prompt_index"] for r in success_requests))
            avg_by_prompt = []
            for pi in prompt_indices:
                lats = [r["latency_seconds"] for r in success_requests if r["prompt_index"] == pi]
                avg_by_prompt.append(np.mean(lats))
            if avg_by_prompt:
                ax7.plot(prompt_indices, avg_by_prompt, marker="o", color="#E67E22", linewidth=2)
                ax7.fill_between(prompt_indices, avg_by_prompt, alpha=0.15, color="#E67E22")
            ax7.set_xlabel("Prompt Index")
            ax7.set_ylabel("Avg Latency (seconds)")
            ax7.set_title("Avg Latency by Prompt Position")
            ax7.xaxis.set_major_locator(ticker.MaxNLocator(integer=True))
            fig7.tight_layout()
            show_fig(fig7)

        # Chart 8: CDF
        st.subheader("5 · Cumulative Latency (CDF)")
        fig8, ax8 = plt.subplots(figsize=(10, 4))
        if latencies:
            sorted_lats = np.sort(latencies)
            cdf = np.arange(1, len(sorted_lats) + 1) / len(sorted_lats)
            ax8.plot(sorted_lats, cdf, color="#2980B9", linewidth=2)
            ax8.axhline(0.5, color="gray", linestyle=":", alpha=0.5, label="P50")
            ax8.axhline(0.95, color="orange", linestyle=":", alpha=0.5, label="P95")
            ax8.axhline(0.99, color="red", linestyle=":", alpha=0.5, label="P99")
            ax8.legend()
        ax8.set_xlabel("Latency (seconds)")
        ax8.set_ylabel("Cumulative Probability")
        ax8.set_title("Latency CDF")
        fig8.tight_layout()
        show_fig(fig8)

        # Percentile summary
        st.subheader("6 · Percentile Summary")
        if latencies:
            percentile_data = {
                "Percentile": ["P10", "P25", "P50 (Median)", "P75", "P90", "P95", "P99", "Max"],
                "Latency (s)": [f"{np.percentile(latencies, p):.4f}" for p in [10, 25, 50, 75, 90, 95, 99, 100]],
            }
            st.table(percentile_data)
        else:
            st.warning("No successful requests to compute percentiles.")

        # Detailed request table
        st.subheader("7 · All Requests (detailed)")
        table_rows = []
        for req in all_requests:
            table_rows.append({
                "Session": req["session_id"],
                "Prompt #": req["prompt_index"],
                "Status": req["status"],
                "Latency (s)": f"{req['latency_seconds']:.4f}",
                "Prompt": req["prompt"][:60],
                "Response": req["response_preview"][:80] if req["response_preview"] else req.get("error_message", "")[:80],
            })
        st.dataframe(table_rows, use_container_width=True)

        # Raw logs
        st.subheader("8 · Raw Log Output")
        if os.path.exists(GEMINI_LOG_FILE):
            with open(GEMINI_LOG_FILE, "r", encoding="utf-8") as f:
                st.code(f.read(), language="log")
        else:
            st.info("No log file found.")

        # Run comparison
        if len(results) > 1:
            st.subheader("9 · Run Comparison")
            col_g, col_h = st.columns(2)
            with col_g:
                fig9, ax9 = plt.subplots(figsize=(7, 4))
                run_labels = [r["run_id"] for r in results[-10:]]
                run_throughputs = []
                for r in results[-10:]:
                    total_r = sum(s["total_prompts"] for s in r["sessions"])
                    tp = total_r / r["total_duration_seconds"] if r["total_duration_seconds"] else 0
                    run_throughputs.append(tp)
                ax9.bar(range(len(run_labels)), run_throughputs, color="#16A085")
                ax9.set_xticks(range(len(run_labels)))
                ax9.set_xticklabels(run_labels, rotation=45, ha="right", fontsize=7)
                ax9.set_ylabel("Throughput (req/s)")
                ax9.set_title("Throughput Across Runs")
                fig9.tight_layout()
                show_fig(fig9)

            with col_h:
                fig10, ax10 = plt.subplots(figsize=(7, 4))
                run_avg_latencies = []
                for r in results[-10:]:
                    lats = [req["latency_seconds"] for s in r["sessions"] for req in s["requests"] if req["status"] == "success"]
                    run_avg_latencies.append(np.mean(lats) if lats else 0)
                ax10.plot(run_labels, run_avg_latencies, marker="s", color="#C0392B", linewidth=2)
                ax10.set_xticklabels(run_labels, rotation=45, ha="right", fontsize=7)
                ax10.set_ylabel("Avg Latency (s)")
                ax10.set_title("Avg Latency Across Runs")
                fig10.tight_layout()
                show_fig(fig10)


# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  TAB 2 – SIMLI + LIVEKIT                                                    ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

with tab_simli:

    with st.expander("Simli + LiveKit Test Configuration", expanded=False):
        sc1, sc2 = st.columns(2)
        simli_api_key = sc1.text_input(
            "Simli API Key", value=os.environ.get("SIMLI_API_KEY", ""), type="password", key="simli_key",
        )
        face_id = sc2.text_input("Face ID", value=os.environ.get("FACE_ID", ""), key="simli_face")
        sc3, sc4, sc5 = st.columns(3)
        lk_api_key = sc3.text_input(
            "LiveKit API Key", value=os.environ.get("LIVEKIT_API_KEY", ""), type="password", key="lk_key",
        )
        lk_api_secret = sc4.text_input(
            "LiveKit API Secret", value=os.environ.get("LIVEKIT_API_SECRET", ""), type="password", key="lk_secret",
        )
        lk_url = sc5.text_input("LiveKit URL", value=os.environ.get("LIVEKIT_URL", ""), key="lk_url")
        simli_sessions = st.slider("Concurrent sessions", 1, 500, 3, key="simli_sessions")
        simli_interval = st.slider(
            "Interval between sessions (seconds)", 0.0, 20.0, 0.0, step=0.1,
            key="simli_interval",
            help="Delay between launching each session. 0 = all at once.",
        )

        run_simli_btn = st.button("🚀 Run Simli Test", key="run_simli", use_container_width=True)

    if run_simli_btn:
        missing = []
        if not simli_api_key:
            missing.append("Simli API Key")
        if not face_id:
            missing.append("Face ID")
        if not lk_api_key:
            missing.append("LiveKit API Key")
        if not lk_api_secret:
            missing.append("LiveKit API Secret")
        if not lk_url:
            missing.append("LiveKit URL")
        if missing:
            st.error(f"Missing: {', '.join(missing)}")
        else:
            with st.spinner(f"Running {simli_sessions} Simli sessions (interval: {simli_interval}s) …"):
                simli_run = asyncio.run(
                    run_simli_test(
                        simli_api_key=simli_api_key,
                        face_id=face_id,
                        lk_api_key=lk_api_key,
                        lk_api_secret=lk_api_secret,
                        lk_url=lk_url,
                        num_sessions=simli_sessions,
                        interval_seconds=simli_interval,
                    )
                )
                save_simli_results(simli_run)
            st.success(f"Simli test **{simli_run.run_id}** completed!")
            st.rerun()

    # ── Load Simli results ─────────────────────────────────────────────────────

    simli_results = _load_json(SIMLI_RESULTS_FILE)

    if not simli_results:
        st.info("No Simli test results yet. Run a test above.")
    else:
        simli_run_ids = [r["run_id"] for r in simli_results]
        simli_selected = st.selectbox(
            "Select Simli test run",
            options=simli_run_ids[::-1],
            format_func=lambda rid: f"Run {rid} – {next(r['concurrent_sessions'] for r in simli_results if r['run_id'] == rid)} sessions",
            key="simli_run_select",
        )
        sdata = next(r for r in simli_results if r["run_id"] == simli_selected)

        # ── KPIs ──────────────────────────────────────────────────────────────
        total_s = len(sdata["sessions"])
        tokens_ok = sdata["total_session_tokens_created"]
        agents_ok = sdata["total_agents_started"]
        tokens_fail = total_s - tokens_ok
        agents_fail = tokens_ok - agents_ok  # only those that got a token could attempt agent start

        # Gather latencies for the two key endpoints
        token_lats = [
            step["latency_seconds"]
            for sess in sdata["sessions"] for step in sess["steps"]
            if step["step"] == "create_simli_session_token" and step["status"] == "success"
        ]
        agent_lats = [
            step["latency_seconds"]
            for sess in sdata["sessions"] for step in sess["steps"]
            if step["step"] == "start_simli_livekit_agent" and step["status"] == "success"
        ]
        avg_token_lat = np.mean(token_lats) if token_lats else 0
        avg_agent_lat = np.mean(agent_lats) if agent_lats else 0

        sk1, sk2, sk3, sk4, sk5, sk6 = st.columns(6)
        sk1.metric("Total Sessions", total_s)
        sk2.metric("Tokens Created", f"{tokens_ok}/{total_s}")
        sk3.metric("Agents Started", f"{agents_ok}/{total_s}")
        sk4.metric("Avg Token Latency", f"{avg_token_lat:.3f}s")
        sk5.metric("Avg Agent Latency", f"{avg_agent_lat:.3f}s")
        sk6.metric("Total Time", f"{sdata['total_duration_seconds']:.2f}s")

        st.divider()

        # ── Chart S1: Success rate pie charts ─────────────────────────────────
        st.subheader("1 · Endpoint Success Rates")
        scol_a, scol_b = st.columns(2)

        with scol_a:
            fig_s1, ax_s1 = plt.subplots(figsize=(5, 4))
            ax_s1.pie(
                [tokens_ok, tokens_fail] if (tokens_ok + tokens_fail) > 0 else [1],
                labels=["Success", "Failed"] if (tokens_ok + tokens_fail) > 0 else ["No data"],
                colors=["#27AE60", "#E74C3C"],
                autopct="%1.1f%%", startangle=90, textprops={"fontsize": 12},
            )
            ax_s1.set_title("/compose/token Success Rate")
            fig_s1.tight_layout()
            show_fig(fig_s1)

        with scol_b:
            fig_s2, ax_s2 = plt.subplots(figsize=(5, 4))
            ax_s2.pie(
                [agents_ok, max(0, agents_fail)] if (agents_ok + max(0, agents_fail)) > 0 else [1],
                labels=["Success", "Failed"] if (agents_ok + max(0, agents_fail)) > 0 else ["No data"],
                colors=["#3498DB", "#E74C3C"],
                autopct="%1.1f%%", startangle=90, textprops={"fontsize": 12},
            )
            ax_s2.set_title("/livekit/agents Success Rate")
            fig_s2.tight_layout()
            show_fig(fig_s2)

        # ── Chart S2: Latency histograms for both endpoints ──────────────────
        st.subheader("2 · Endpoint Latency Distribution")
        scol_c, scol_d = st.columns(2)

        with scol_c:
            fig_s3, ax_s3 = plt.subplots(figsize=(7, 4))
            if token_lats:
                ax_s3.hist(token_lats, bins=max(5, len(token_lats) // 2), color="#27AE60", edgecolor="white", alpha=0.85)
                ax_s3.axvline(avg_token_lat, color="red", linestyle="--", linewidth=1.5, label=f"Mean = {avg_token_lat:.3f}s")
                if len(token_lats) > 1:
                    p95_t = np.percentile(token_lats, 95)
                    ax_s3.axvline(p95_t, color="orange", linestyle="--", linewidth=1.5, label=f"P95 = {p95_t:.3f}s")
                ax_s3.legend()
            ax_s3.set_xlabel("Latency (seconds)")
            ax_s3.set_ylabel("Count")
            ax_s3.set_title("/compose/token Latency")
            fig_s3.tight_layout()
            show_fig(fig_s3)

        with scol_d:
            fig_s4, ax_s4 = plt.subplots(figsize=(7, 4))
            if agent_lats:
                ax_s4.hist(agent_lats, bins=max(5, len(agent_lats) // 2), color="#3498DB", edgecolor="white", alpha=0.85)
                ax_s4.axvline(avg_agent_lat, color="red", linestyle="--", linewidth=1.5, label=f"Mean = {avg_agent_lat:.3f}s")
                if len(agent_lats) > 1:
                    p95_a = np.percentile(agent_lats, 95)
                    ax_s4.axvline(p95_a, color="orange", linestyle="--", linewidth=1.5, label=f"P95 = {p95_a:.3f}s")
                ax_s4.legend()
            ax_s4.set_xlabel("Latency (seconds)")
            ax_s4.set_ylabel("Count")
            ax_s4.set_title("/livekit/agents Latency")
            fig_s4.tight_layout()
            show_fig(fig_s4)

        # ── Chart S3: Step latency breakdown (stacked bar per session) ────────
        st.subheader("3 · Step Latency Breakdown per Session")

        step_names = ["generate_livekit_token", "create_simli_session_token", "start_simli_livekit_agent"]
        step_labels = ["Generate LK Token", "Create Session Token", "Start Agent"]
        step_colors = ["#95A5A6", "#27AE60", "#3498DB"]
        fig_s5, ax_s5 = plt.subplots(figsize=(14, 5))
        x_pos = np.arange(total_s)
        bottom = np.zeros(total_s)

        for sn, slabel, color in zip(step_names, step_labels, step_colors):
            vals = []
            for sess in sdata["sessions"]:
                step_lat = 0
                for step in sess["steps"]:
                    if step["step"] == sn:
                        step_lat = step["latency_seconds"]
                        break
                vals.append(step_lat)
            ax_s5.bar(x_pos, vals, bottom=bottom, label=slabel, color=color, edgecolor="white")
            bottom += np.array(vals)

        ax_s5.set_xticks(x_pos)
        ax_s5.set_xticklabels([f"S{s['session_id']}" for s in sdata["sessions"]], fontsize=8)
        ax_s5.set_xlabel("Session")
        ax_s5.set_ylabel("Latency (seconds)")
        ax_s5.set_title("Step Latency Breakdown (stacked)")
        ax_s5.legend(loc="upper right", fontsize=8)
        fig_s5.tight_layout()
        show_fig(fig_s5)

        # ── Chart S4: Timeline (Gantt-style) ─────────────────────────────────
        st.subheader("4 · Session Timeline")

        all_steps_flat = [(s["session_id"], step) for s in sdata["sessions"] for step in s["steps"]]
        fig_s6, ax_s6 = plt.subplots(figsize=(14, min(40, max(4, len(all_steps_flat) * 0.3))))
        sbase = sdata["start_time"]
        step_color_map = dict(zip(step_names, step_colors))

        for i, (sid, step) in enumerate(sorted(all_steps_flat, key=lambda x: (x[0], x[1]["start_time"]))):
            start_rel = step["start_time"] - sbase
            dur = step["latency_seconds"]
            c = step_color_map.get(step["step"], "gray")
            if step["status"] == "error":
                c = "#E74C3C"
            ax_s6.barh(i, dur, left=start_rel, height=0.7, color=c, edgecolor="white", linewidth=0.3)

        ax_s6.set_xlabel("Time since test start (seconds)")
        ax_s6.set_ylabel("Step #")
        ax_s6.set_title("Step Timeline (gray=token gen, green=session token, blue=agent start, red=error)")
        ax_s6.invert_yaxis()
        fig_s6.tight_layout()
        show_fig(fig_s6)

        # ── Chart S5: Avg latency per step + session durations ────────────────
        st.subheader("5 · Per-Step Avg Latency & Session Duration")
        scol_e, scol_f = st.columns(2)

        with scol_e:
            fig_s7, ax_s7 = plt.subplots(figsize=(7, 4))
            step_avgs = []
            for sn in step_names:
                lats = [
                    step["latency_seconds"]
                    for sess in sdata["sessions"] for step in sess["steps"]
                    if step["step"] == sn and step["status"] == "success"
                ]
                step_avgs.append(np.mean(lats) if lats else 0)
            ax_s7.barh(step_labels, step_avgs, color=step_colors)
            ax_s7.set_xlabel("Avg Latency (seconds)")
            ax_s7.set_title("Average Latency per Step")
            fig_s7.tight_layout()
            show_fig(fig_s7)

        with scol_f:
            fig_s8, ax_s8 = plt.subplots(figsize=(7, 4))
            s_ids = [f"S{s['session_id']}" for s in sdata["sessions"]]
            s_durations = [s["total_duration_seconds"] for s in sdata["sessions"]]
            s_colors_bar = ["#27AE60" if s["status"] == "success" else "#E74C3C" for s in sdata["sessions"]]
            ax_s8.bar(s_ids, s_durations, color=s_colors_bar)
            ax_s8.set_xlabel("Session")
            ax_s8.set_ylabel("Duration (seconds)")
            ax_s8.set_title("Session Duration (green=success, red=error)")
            fig_s8.tight_layout()
            show_fig(fig_s8)

        # ── Chart S6: CDF for both endpoints ─────────────────────────────────
        st.subheader("6 · Endpoint Latency CDF")
        fig_s9, ax_s9 = plt.subplots(figsize=(10, 4))
        if token_lats:
            sorted_tl = np.sort(token_lats)
            cdf_tl = np.arange(1, len(sorted_tl) + 1) / len(sorted_tl)
            ax_s9.plot(sorted_tl, cdf_tl, color="#27AE60", linewidth=2, label="/compose/token")
        if agent_lats:
            sorted_al = np.sort(agent_lats)
            cdf_al = np.arange(1, len(sorted_al) + 1) / len(sorted_al)
            ax_s9.plot(sorted_al, cdf_al, color="#3498DB", linewidth=2, label="/livekit/agents")
        ax_s9.axhline(0.5, color="gray", linestyle=":", alpha=0.5)
        ax_s9.axhline(0.95, color="orange", linestyle=":", alpha=0.5)
        ax_s9.legend()
        ax_s9.set_xlabel("Latency (seconds)")
        ax_s9.set_ylabel("Cumulative Probability")
        ax_s9.set_title("Endpoint Latency CDF")
        fig_s9.tight_layout()
        show_fig(fig_s9)

        # ── Chart S7: Step success/failure ────────────────────────────────────
        st.subheader("7 · Step Success / Failure")
        fig_s10, ax_s10 = plt.subplots(figsize=(10, 4))
        step_success_counts = []
        step_error_counts = []
        for sn in step_names:
            ok = sum(1 for sess in sdata["sessions"] for step in sess["steps"] if step["step"] == sn and step["status"] == "success")
            err = sum(1 for sess in sdata["sessions"] for step in sess["steps"] if step["step"] == sn and step["status"] == "error")
            step_success_counts.append(ok)
            step_error_counts.append(err)
        x_st = np.arange(len(step_names))
        w = 0.35
        ax_s10.bar(x_st - w / 2, step_success_counts, w, label="Success", color="#27AE60")
        ax_s10.bar(x_st + w / 2, step_error_counts, w, label="Error", color="#E74C3C")
        ax_s10.set_xticks(x_st)
        ax_s10.set_xticklabels(step_labels, fontsize=9)
        ax_s10.yaxis.set_major_locator(ticker.MaxNLocator(integer=True))
        ax_s10.set_ylabel("Count")
        ax_s10.set_title("Step Outcome Breakdown")
        ax_s10.legend()
        fig_s10.tight_layout()
        show_fig(fig_s10)

        # ── Percentile Tables ────────────────────────────────────────────────
        st.subheader("8 · Latency Percentiles")
        pcol1, pcol2 = st.columns(2)
        with pcol1:
            st.markdown("**/compose/token**")
            if token_lats:
                st.table({
                    "Percentile": ["P10", "P25", "P50", "P75", "P90", "P95", "P99", "Max"],
                    "Latency (s)": [f"{np.percentile(token_lats, p):.4f}" for p in [10, 25, 50, 75, 90, 95, 99, 100]],
                })
            else:
                st.warning("No successful token requests.")
        with pcol2:
            st.markdown("**/livekit/agents**")
            if agent_lats:
                st.table({
                    "Percentile": ["P10", "P25", "P50", "P75", "P90", "P95", "P99", "Max"],
                    "Latency (s)": [f"{np.percentile(agent_lats, p):.4f}" for p in [10, 25, 50, 75, 90, 95, 99, 100]],
                })
            else:
                st.warning("No successful agent start requests.")

        # ── Detailed step table ──────────────────────────────────────────────
        st.subheader("9 · All Steps (detailed)")
        step_rows = []
        for sess in sdata["sessions"]:
            for step in sess["steps"]:
                step_rows.append({
                    "Session": sess["session_id"],
                    "Room": sess["room_name"],
                    "Step": step["step"].replace("_", " ").title(),
                    "Status": step["status"],
                    "Latency (s)": f"{step['latency_seconds']:.4f}",
                    "Detail": step["detail"][:80],
                    "Error": (step.get("error_message") or "")[:80],
                })
        st.dataframe(step_rows, use_container_width=True)

        # ── Raw logs ─────────────────────────────────────────────────────────
        st.subheader("10 · Raw Log Output")
        if os.path.exists(SIMLI_LOG_FILE):
            with open(SIMLI_LOG_FILE, "r", encoding="utf-8") as f:
                st.code(f.read(), language="log")
        else:
            st.info("No log file found.")

        # ── Run comparison ───────────────────────────────────────────────────
        if len(simli_results) > 1:
            st.subheader("11 · Run Comparison")
            scol_g, scol_h = st.columns(2)
            with scol_g:
                fig_s11, ax_s11 = plt.subplots(figsize=(7, 4))
                srun_labels = [r["run_id"] for r in simli_results[-10:]]
                srun_token_rates = [
                    r["total_session_tokens_created"] / r["concurrent_sessions"] * 100 if r["concurrent_sessions"] else 0
                    for r in simli_results[-10:]
                ]
                srun_agent_rates = [
                    r["total_agents_started"] / r["concurrent_sessions"] * 100 if r["concurrent_sessions"] else 0
                    for r in simli_results[-10:]
                ]
                x_run = np.arange(len(srun_labels))
                ax_s11.bar(x_run - 0.2, srun_token_rates, 0.35, label="Token Success %", color="#27AE60")
                ax_s11.bar(x_run + 0.2, srun_agent_rates, 0.35, label="Agent Success %", color="#3498DB")
                ax_s11.set_xticks(x_run)
                ax_s11.set_xticklabels(srun_labels, rotation=45, ha="right", fontsize=7)
                ax_s11.set_ylabel("Success Rate (%)")
                ax_s11.set_title("Endpoint Success Rate Across Runs")
                ax_s11.set_ylim(0, 105)
                ax_s11.legend(fontsize=8)
                fig_s11.tight_layout()
                show_fig(fig_s11)

            with scol_h:
                fig_s12, ax_s12 = plt.subplots(figsize=(7, 4))
                srun_avg_token = []
                srun_avg_agent = []
                for r in simli_results[-10:]:
                    tl = [step["latency_seconds"] for s in r["sessions"] for step in s["steps"] if step["step"] == "create_simli_session_token" and step["status"] == "success"]
                    al = [step["latency_seconds"] for s in r["sessions"] for step in s["steps"] if step["step"] == "start_simli_livekit_agent" and step["status"] == "success"]
                    srun_avg_token.append(np.mean(tl) if tl else 0)
                    srun_avg_agent.append(np.mean(al) if al else 0)
                ax_s12.plot(srun_labels, srun_avg_token, marker="o", color="#27AE60", linewidth=2, label="/compose/token")
                ax_s12.plot(srun_labels, srun_avg_agent, marker="s", color="#3498DB", linewidth=2, label="/livekit/agents")
                ax_s12.set_xticklabels(srun_labels, rotation=45, ha="right", fontsize=7)
                ax_s12.set_ylabel("Avg Latency (s)")
                ax_s12.set_title("Avg Endpoint Latency Across Runs")
                ax_s12.legend(fontsize=8)
                fig_s12.tight_layout()
                show_fig(fig_s12)
