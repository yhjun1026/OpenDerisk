"""Alibaba Cloud Wanxiang (通义万相) Image Generation Provider.

Implements image generation via the DashScope API, supporting:
- wan2.6-t2i (sync API, newest)
- wan2.5-t2i-preview, wan2.2-t2i-flash, wan2.2-t2i-plus
- wanx2.1-t2i-turbo, wanx2.1-t2i-plus
- wanx2.0-t2i-turbo
- wanx-v1 (legacy)

API docs: https://help.aliyun.com/zh/model-studio/text-to-image-v2-api-reference
"""

import asyncio
import logging
from typing import Any, List, Optional

from derisk.agent.util.media_gen.base import MediaGenProvider, MediaGenResult
from derisk.agent.util.media_gen.provider_registry import MediaGenProviderRegistry

logger = logging.getLogger(__name__)

# Models that use the new sync/async multimodal-generation API (wan2.6+)
_NEW_API_MODELS = {"wan2.6-t2i"}

# Models that use the legacy text2image/image-synthesis async API
_LEGACY_API_MODELS = {
    "wan2.5-t2i-preview",
    "wan2.2-t2i-flash",
    "wan2.2-t2i-plus",
    "wanx2.1-t2i-turbo",
    "wanx2.1-t2i-plus",
    "wanx2.0-t2i-turbo",
    "wanx-v1",
}

# All supported models
_ALL_MODELS = _NEW_API_MODELS | _LEGACY_API_MODELS

# Default base URLs
_DEFAULT_BASE_URL = "https://dashscope.aliyuncs.com"

# API endpoints
_SYNC_ENDPOINT = "/api/v1/services/aigc/multimodal-generation/generation"
_ASYNC_CREATE_ENDPOINT = "/api/v1/services/aigc/image-generation/generation"
_LEGACY_ASYNC_ENDPOINT = "/api/v1/services/aigc/text2image/image-synthesis"
_TASK_QUERY_ENDPOINT = "/api/v1/tasks/{task_id}"

# Style mappings for legacy models (wanx-v1)
_STYLE_MAP = {
    "auto": "<auto>",
    "photography": "<photography>",
    "portrait": "<portrait>",
    "3d_cartoon": "<3d cartoon>",
    "anime": "<anime>",
    "oil_painting": "<oil painting>",
    "watercolor": "<watercolor>",
    "sketch": "<sketch>",
    "chinese_painting": "<chinese painting>",
    "flat_illustration": "<flat illustration>",
}

# Size mappings for legacy models
_SIZE_MAP = {
    "1024x1024": "1024*1024",
    "720x1280": "720*1280",
    "768x1152": "768*1152",
    "1280x720": "1280*720",
}


@MediaGenProviderRegistry.register(name="wanxiang", env_key="DASHSCOPE_API_KEY")
class WanxiangImageProvider(MediaGenProvider):
    """Alibaba Cloud Wanxiang (通义万相) image generation provider.

    Supports both the new V2 API (wan2.6 sync/async) and the legacy V1 API.
    Uses the DashScope API with async task polling for older models.
    """

    def supported_image_models(self) -> List[str]:
        return sorted(_ALL_MODELS)

    def supported_video_models(self) -> List[str]:
        return []

    async def generate_image(
        self,
        prompt: str,
        model: str = "wan2.6-t2i",
        **kwargs: Any,
    ) -> MediaGenResult:
        """Generate an image using Alibaba Cloud Wanxiang API.

        Args:
            prompt: Text description of the image (supports Chinese & English).
            model: Model to use (wan2.6-t2i, wan2.5-t2i-preview, wanx2.1-t2i-turbo, etc.).
            **kwargs: Additional params:
                - size: Image size ("1024x1024", "1280*1280", "720*1280", etc.)
                - n: Number of images (1-4, default 1)
                - style: Image style (for legacy models: "auto", "photography", etc.)
                - negative_prompt: Negative prompt (content to avoid)
                - watermark: Whether to add AI watermark (default False)
                - seed: Random seed for reproducibility
                - timeout: Max wait time in seconds (default 180)
        """
        try:
            import httpx
        except ImportError:
            raise ImportError(
                "httpx package is required for Wanxiang image generation. "
                "Install with: pip install httpx"
            )

        timeout = kwargs.get("timeout", 180)
        base_url = self.base_url or _DEFAULT_BASE_URL

        # Route to appropriate API based on model
        if model in _NEW_API_MODELS:
            return await self._generate_via_new_api(
                httpx, prompt, model, base_url, timeout, **kwargs
            )
        else:
            return await self._generate_via_legacy_api(
                httpx, prompt, model, base_url, timeout, **kwargs
            )

    async def _generate_via_new_api(
        self,
        httpx_module: Any,
        prompt: str,
        model: str,
        base_url: str,
        timeout: int,
        **kwargs: Any,
    ) -> MediaGenResult:
        """Generate image using the new V2 API (wan2.6+).

        Supports both sync (single request) and async (submit -> poll) modes.
        For wan2.6, sync mode is preferred as it's simpler and faster.
        """
        headers = self._build_headers(sync_mode=False)

        size = self._normalize_size(kwargs.get("size", "1280*1280"))
        n = kwargs.get("n", 1)
        negative_prompt = kwargs.get("negative_prompt", "")
        watermark = kwargs.get("watermark", False)
        seed = kwargs.get("seed")

        # Build request body (new messages format)
        body: dict[str, Any] = {
            "model": model,
            "input": {
                "messages": [
                    {
                        "role": "user",
                        "content": [{"text": prompt}],
                    }
                ]
            },
            "parameters": {
                "size": size,
                "n": n,
                "watermark": watermark,
            },
        }

        if negative_prompt:
            body["parameters"]["negative_prompt"] = negative_prompt
        if seed is not None:
            body["parameters"]["seed"] = seed

        logger.info(
            f"[WanxiangImageProvider] Generating image via new API: "
            f"model={model}, size={size}, n={n}"
        )

        # Use async task mode (create -> poll)
        async with httpx_module.AsyncClient(timeout=timeout) as client:
            # Step 1: Create task
            create_url = f"{base_url}{_ASYNC_CREATE_ENDPOINT}"
            resp = await client.post(create_url, headers=headers, json=body)
            resp.raise_for_status()
            result = resp.json()

            task_id = result.get("output", {}).get("task_id")
            if not task_id:
                raise ValueError(f"Wanxiang API returned no task_id: {result}")

            logger.info(f"[WanxiangImageProvider] Task created: {task_id}")

            # Step 2: Poll for completion
            image_url = await self._poll_task(
                client, base_url, task_id, timeout, is_new_api=True
            )

            # Step 3: Download image
            logger.info(f"[WanxiangImageProvider] Downloading image from {image_url}")
            dl_resp = await client.get(image_url)
            dl_resp.raise_for_status()

            width, height = self._parse_dimensions(size)

            return MediaGenResult(
                data=dl_resp.content,
                format="png",
                mime_type="image/png",
                width=width,
                height=height,
                metadata={
                    "model": model,
                    "size": size,
                    "n": n,
                    "task_id": task_id,
                    "provider": "wanxiang",
                    "image_url": image_url,
                },
            )

    async def _generate_via_legacy_api(
        self,
        httpx_module: Any,
        prompt: str,
        model: str,
        base_url: str,
        timeout: int,
        **kwargs: Any,
    ) -> MediaGenResult:
        """Generate image using the legacy V1/V2 async API (wanx-v1, wan2.5 and below).

        Uses the text2image/image-synthesis endpoint with async polling.
        """
        headers = self._build_headers(sync_mode=True)

        size = self._normalize_size(kwargs.get("size", "1024x1024"))
        n = kwargs.get("n", 1)
        style = kwargs.get("style", "auto")
        negative_prompt = kwargs.get("negative_prompt", "")
        seed = kwargs.get("seed")

        # Build request body (legacy input.prompt format)
        input_obj: dict[str, Any] = {"prompt": prompt}
        if negative_prompt:
            input_obj["negative_prompt"] = negative_prompt

        parameters: dict[str, Any] = {
            "size": size,
            "n": n,
        }

        # Style only for wanx-v1
        if model == "wanx-v1":
            style_value = _STYLE_MAP.get(style, style)
            if not style_value.startswith("<"):
                style_value = f"<{style_value}>"
            parameters["style"] = style_value

        if seed is not None:
            parameters["seed"] = seed

        body = {
            "model": model,
            "input": input_obj,
            "parameters": parameters,
        }

        logger.info(
            f"[WanxiangImageProvider] Generating image via legacy API: "
            f"model={model}, size={size}, n={n}, style={style}"
        )

        async with httpx_module.AsyncClient(timeout=timeout) as client:
            # Step 1: Create task
            create_url = f"{base_url}{_LEGACY_ASYNC_ENDPOINT}"
            resp = await client.post(create_url, headers=headers, json=body)
            resp.raise_for_status()
            result = resp.json()

            task_id = result.get("output", {}).get("task_id")
            if not task_id:
                raise ValueError(f"Wanxiang API returned no task_id: {result}")

            logger.info(f"[WanxiangImageProvider] Task created: {task_id}")

            # Step 2: Poll for completion
            image_url = await self._poll_task(
                client, base_url, task_id, timeout, is_new_api=False
            )

            # Step 3: Download image
            logger.info(f"[WanxiangImageProvider] Downloading image from {image_url}")
            dl_resp = await client.get(image_url)
            dl_resp.raise_for_status()

            width, height = self._parse_dimensions(size)

            metadata: dict[str, Any] = {
                "model": model,
                "size": size,
                "n": n,
                "task_id": task_id,
                "provider": "wanxiang",
                "image_url": image_url,
            }
            if model == "wanx-v1":
                metadata["style"] = style

            return MediaGenResult(
                data=dl_resp.content,
                format="png",
                mime_type="image/png",
                width=width,
                height=height,
                metadata=metadata,
            )

    def _build_headers(self, sync_mode: bool = False) -> dict[str, str]:
        """Build HTTP headers for DashScope API."""
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        if sync_mode:
            # Legacy API requires X-DashScope-Async: enable
            headers["X-DashScope-Async"] = "enable"
        return headers

    async def _poll_task(
        self,
        client: Any,
        base_url: str,
        task_id: str,
        timeout: int,
        is_new_api: bool = True,
    ) -> str:
        """Poll DashScope task until completion, return image URL.

        Args:
            client: httpx.AsyncClient instance.
            base_url: DashScope base URL.
            task_id: Task ID to poll.
            timeout: Maximum wait time in seconds.
            is_new_api: If True, parse new API response format (choices.message.content.image).
                        If False, parse legacy format (results[].url).

        Returns:
            Image URL string.
        """
        query_url = f"{base_url}{_TASK_QUERY_ENDPOINT.format(task_id=task_id)}"
        headers = {"Authorization": f"Bearer {self.api_key}"}

        poll_interval = 5  # seconds
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
                if is_new_api:
                    # New API: output.choices[0].message.content[0].image
                    choices = output.get("choices", [])
                    if choices:
                        content = choices[0].get("message", {}).get("content", [])
                        for item in content:
                            if item.get("type") == "image" and item.get("image"):
                                return item["image"]
                    raise ValueError(
                        f"Task succeeded but no image URL found in response: {data}"
                    )
                else:
                    # Legacy API: output.results[0].url
                    results = output.get("results", [])
                    if results:
                        url = results[0].get("url")
                        if url:
                            return url
                    raise ValueError(
                        f"Task succeeded but no image URL found in results: {data}"
                    )

            elif status in ("FAILED", "CANCELED", "UNKNOWN"):
                error_msg = output.get("message", "") or data.get("message", "")
                raise RuntimeError(
                    f"Wanxiang image generation failed (status={status}): {error_msg}"
                )

            logger.debug(
                f"[WanxiangImageProvider] Task {task_id} status: {status} "
                f"({elapsed}s elapsed)"
            )

        raise TimeoutError(
            f"Wanxiang image generation timed out after {timeout}s (task_id={task_id})"
        )

    def _normalize_size(self, size: str) -> str:
        """Normalize size format to DashScope format (width*height)."""
        # Convert "1024x1024" to "1024*1024" if needed
        if "x" in size and "*" not in size:
            return size.replace("x", "*")
        return size

    def _parse_dimensions(self, size: str) -> tuple[Optional[int], Optional[int]]:
        """Parse width and height from size string."""
        separator = "*" if "*" in size else "x"
        if separator in size:
            parts = size.split(separator)
            if len(parts) == 2:
                try:
                    return int(parts[0]), int(parts[1])
                except ValueError:
                    pass
        return None, None

    async def generate_video(
        self,
        prompt: str,
        model: str = "",
        **kwargs: Any,
    ) -> MediaGenResult:
        raise NotImplementedError(
            "Wanxiang image provider does not support video generation"
        )
