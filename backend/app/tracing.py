"""
Observability via Langfuse v2.
v2 API: lf.trace() creates a trace, trace.span() creates spans.
"""
from app.config import settings


def get_langfuse():
    if not settings.langfuse_public_key or not settings.langfuse_secret_key:
        print("[tracing] Langfuse keys not set — tracing disabled")
        return None
    try:
        from langfuse import Langfuse
        return Langfuse(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            host=settings.langfuse_host,
        )
    except Exception as e:
        print(f"[tracing] Langfuse init failed: {e}")
        return None


def trace_agent_run(
    thread_id: str,
    customer_id: int,
    message: str,
    result: dict,
    duration_ms: float,
) -> None:
    lf = get_langfuse()
    if not lf:
        return

    try:
        action = result.get("action", "none")
        interrupted = bool(result.get("__interrupt__"))
        context_chunks = len(result.get("context", []))

        trace = lf.trace(
            name="agent-run",
            input={"message": message, "customer_id": customer_id},
            output={
                "draft": result.get("draft", "")[:500],
                "grounded": result.get("grounded"),
                "escalate": result.get("escalate"),
                "action": action,
                "pending_approval": interrupted,
            },
            metadata={
                "thread_id": thread_id,
                "route_decision": result.get("route_decision"),
                "best_vector_score": result.get("best_score"),
                "context_chunks": context_chunks,
                "memory_count": len(result.get("memories", [])),
                "duration_ms": round(duration_ms, 2),
                "model": settings.llm_model,
            },
            tags=["support-copilot"],
        )

        if context_chunks > 0:
            trace.span(
                name="retrieval",
                input={"query": message},
                output={
                    "chunks_found": context_chunks,
                    "best_vector_score": round(result.get("best_score", 0), 4),
                },
            )

        if result.get("grounded") is not None:
            trace.span(
                name="grounding-check",
                output={
                    "grounded": result.get("grounded"),
                    "escalate": result.get("escalate"),
                },
            )

        if action and action != "none":
            trace.span(
                name="action-decision",
                output={
                    "action": action,
                    "reason": result.get("action_reason", ""),
                    "needs_approval": interrupted,
                },
            )

        action_result = result.get("action_result")
        if action_result:
            trace.span(
                name="action-execution",
                output=action_result,
            )

        lf.flush()
        print(f"[tracing] trace sent — thread={thread_id}")

    except Exception as e:
        print(f"[tracing] trace failed (non-fatal): {e}")


def trace_approval(
    thread_id: str,
    action: str,
    approved: bool,
    result: dict,
) -> None:
    lf = get_langfuse()
    if not lf:
        return
    try:
        lf.trace(
            name="approval-decision",
            input={"thread_id": thread_id, "action": action, "approved": approved},
            output=result.get("action_result") or {},
            tags=["support-copilot", "approval"],
        )
        lf.flush()
    except Exception as e:
        print(f"[tracing] approval trace failed (non-fatal): {e}")