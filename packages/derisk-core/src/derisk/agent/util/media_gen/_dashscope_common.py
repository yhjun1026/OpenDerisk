"""Shared DashScope HTTP plumbing for media-gen providers.

DashScope (Alibaba Cloud Model Studio) providers share:
- Bearer auth + an optional `X-DashScope-Async: enable` header
- The async task polling protocol: GET /api/v1/tasks/{task_id}, parsing
  ``output.task_status`` (PENDING/RUNNING -> SUCCEEDED/FAILED/CANCELED/UNKNOWN)

This module centralizes that plumbing so providers (wanxiang image,
happyhorse video, ...) stay thin. Sync endpoints (e.g. qwen-image-3.0-pro
via multimodal-generation/generation) only use ``build_headers`` and
``raise_for_error`` -- they do not poll.
"""

import asyncio
import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://dashscope.aliyuncs.com"
TASK_QUERY_PATH = "/api/v1/tasks/{task_id}"

# Terminal failure statuses returned by /api/v1/tasks/{task_id}
_FAILED_STATUSES = ("FAILED", "CANCELED", "UNKNOWN")


def build_headers(api_key: str, *, async_mode: bool = False) -> dict[str, str]:
    """Build DashScope request headers.

    Args:
        api_key: DashScope API key.
        async_mode: If True, add ``X-DashScope-Async: enable``. Required by
            some async endpoints (text2image/image-synthesis,
            video-generation/video-synthesis). The newer image-generation and
            multimodal-generation endpoints are async-by-default / sync and
            do not need this header.
    """
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    if async_mode:
        headers["X-DashScope-Async"] = "enable"
    return headers


def raise_for_error(result: dict, provider: str = "dashscope") -> None:
    """Raise RuntimeError if a DashScope response carries a top-level error.

    DashScope signals errors with a top-level ``code``/``message`` pair
    (success responses omit ``code``). This is shared by both the create
    endpoints and the sync multimodal endpoint.
    """
    code = result.get("code")
    if code:
        raise RuntimeError(
            f"{provider} request failed ({code}): {result.get('message', '')}"
        )


async def poll_dashscope_task(
    client: Any,
    base_url: str,
    task_id: str,
    api_key: str,
    timeout: int,
    extract_url: Callable[[dict], str],
    poll_interval: int = 10,
    provider: str = "dashscope",
) -> str:
    """Poll a DashScope async task until completion, return the result URL.

    Args:
        client: httpx.AsyncClient instance.
        base_url: DashScope base URL.
        task_id: Task ID returned by the create endpoint.
        api_key: DashScope API key.
        timeout: Maximum wait time in seconds.
        extract_url: Callable(full_response_dict) -> URL string. Should raise
            ValueError if the URL cannot be located in a SUCCEEDED response.
        poll_interval: Seconds between polls.
        provider: Provider name for log/error messages.

    Returns:
        Result URL string (image or video).

    Raises:
        RuntimeError: task reached a FAILED/CANCELED/UNKNOWN status.
        TimeoutError: task did not finish within ``timeout``.
    """
    query_url = f"{base_url}{TASK_QUERY_PATH.format(task_id=task_id)}"
    headers = {"Authorization": f"Bearer {api_key}"}

    elapsed = 0
    while elapsed < timeout:
        await asyncio.sleep(poll_interval)
        elapsed += poll_interval

        resp = await client.get(query_url, headers=headers)
        resp.raise_for_status()
        data = resp.json()

        output = data.get("output", {})
        status = output.get("task_status", "")

        if status == "SUCCEEDED":
            return extract_url(data)

        if status in _FAILED_STATUSES:
            error_msg = (
                output.get("message", "")
                or output.get("code", "")
                or data.get("message", "")
                or f"task status {status}"
            )
            raise RuntimeError(
                f"{provider} task failed (status={status}): {error_msg}"
            )

        logger.debug(
            f"[{provider}] Task {task_id} status: {status} ({elapsed}s elapsed)"
        )

    raise TimeoutError(
        f"{provider} task timed out after {timeout}s (task_id={task_id})"
    )
