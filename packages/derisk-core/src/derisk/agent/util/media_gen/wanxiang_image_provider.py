"""Alibaba Cloud Wanxiang (通义万相) Image Generation Provider.

Implements image generation via the DashScope API, supporting:
- wan2.6-t2i (sync API, newest)
- wan2.5-t2i-preview, wan2.2-t2i-flash, wan2.2-t2i-plus
- wanx2.1-t2i-turbo, wanx2.1-t2i-plus
- wanx2.0-t2i-turbo
- wanx-v1 (legacy)

API docs: https://help.aliyun.com/zh/model-studio/text-to-image-v2-api-reference
"""

import logging
from typing import Any, List, Optional

from derisk.agent.util.media_gen._dashscope_common import (
    build_headers,
    poll_dashscope_task,
    raise_for_error,
)
from derisk.agent.util.media_gen.base import MediaGenProvider, MediaGenResult
from derisk.agent.util.media_gen.provider_registry import MediaGenProviderRegistry

logger = logging.getLogger(__name__)

# Model names are free-form (protocol-based routing). The image API shape is
# selected by model-name prefix (stable families, so new versions need no code
# change):
#   qwen-image* -> sync multimodal-generation (qwen-image-3.0-pro, future qwen-image-*)
#   wan2.*      -> async image-generation (wan2.6-t2i, future wan2.*)
#   else        -> legacy async text2image (wanx*)

# Default base URLs
_DEFAULT_BASE_URL = "https://dashscope.aliyuncs.com"

# API endpoints
_QWEN_SYNC_ENDPOINT = "/api/v1/services/aigc/multimodal-generation/generation"
_ASYNC_CREATE_ENDPOINT = "/api/v1/services/aigc/image-generation/generation"
_LEGACY_ASYNC_ENDPOINT = "/api/v1/services/aigc/text2image/image-synthesis"

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


def _extract_new_api_image(data: dict) -> str:
    """Extract image URL from a SUCCEEDED new-API (wan2.6) task response."""
    output = data.get("output", {})
    choices = output.get("choices", [])
    if choices:
        content = choices[0].get("message", {}).get("content", [])
        for item in content:
            if item.get("type") == "image" and item.get("image"):
                return item["image"]
    raise ValueError(f"Task succeeded but no image URL found in response: {data}")


def _extract_legacy_image(data: dict) -> str:
    """Extract image URL from a SUCCEEDED legacy-API task response."""
    output = data.get("output", {})
    results = output.get("results", [])
    if results:
        url = results[0].get("url")
        if url:
            return url
    raise ValueError(f"Task succeeded but no image URL found in results: {data}")


@MediaGenProviderRegistry.register(protocol="dashscope_image", env_key="DASHSCOPE_API_KEY")
class WanxiangImageProvider(MediaGenProvider):
    """Alibaba Cloud Wanxiang / Qwen-Image (通义万相 / 千问图像) provider.

    Routes by model-name prefix (free-form model names):
    - qwen-image* -> sync multimodal-generation endpoint (T2I + I2I 1-3 imgs)
    - wan2.*      -> async image-generation endpoint (task polling)
    - else        -> legacy async text2image endpoint (task polling)
    """

    def supported_image_models(self) -> List[str]:
        return []

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

        # Route to appropriate API based on model-name prefix (free-form)
        if model.startswith("qwen-image"):
            return await self._generate_via_qwen_sync(
                httpx, prompt, model, base_url, timeout, **kwargs
            )
        elif model.startswith("wan2."):
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
            image_url = await poll_dashscope_task(
                client, base_url, task_id, self.api_key, timeout,
                extract_url=_extract_new_api_image,
                poll_interval=5,
                provider="wanxiang",
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
            image_url = await poll_dashscope_task(
                client, base_url, task_id, self.api_key, timeout,
                extract_url=_extract_legacy_image,
                poll_interval=5,
                provider="wanxiang",
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

    async def _generate_via_qwen_sync(
        self,
        httpx_module: Any,
        prompt: str,
        model: str,
        base_url: str,
        timeout: int,
        **kwargs: Any,
    ) -> MediaGenResult:
        """Generate image via the sync multimodal-generation endpoint.

        Used by qwen-image-3.0-pro. Supports:
        - T2I (text only)
        - I2I / image editing (1-3 reference images + text)

        This endpoint is synchronous: the image URL is returned directly in
        the response (no task polling).
        """
        headers = build_headers(self.api_key, async_mode=False)

        size = kwargs.get("size")
        n = kwargs.get("n", 1)
        negative_prompt = kwargs.get("negative_prompt", "")
        seed = kwargs.get("seed")
        watermark = kwargs.get("watermark", False)
        prompt_extend = kwargs.get("prompt_extend", True)
        image_url = kwargs.get("image_url")
        reference_images = kwargs.get("reference_images")

        # Collect input images for I2I (1-3); reference_images takes precedence
        images: list[str] = []
        if reference_images:
            if not isinstance(reference_images, (list, tuple)):
                raise ValueError("reference_images must be a list of URL strings")
            images = [u for u in reference_images if u]
        elif image_url:
            images = [image_url]
        if len(images) > 3:
            raise ValueError(
                f"qwen-image-3.0 I2I supports at most 3 reference images, "
                f"got {len(images)}"
            )

        # Build content: images first, then a single text (per API spec)
        content: list[dict[str, Any]] = [{"image": u} for u in images]
        content.append({"text": prompt})

        parameters: dict[str, Any] = {
            "prompt_extend": prompt_extend,
            "watermark": watermark,
        }
        if size:
            parameters["size"] = self._normalize_size(size)
        if n and n != 1:
            parameters["n"] = n
        if negative_prompt:
            parameters["negative_prompt"] = negative_prompt
        if seed is not None:
            parameters["seed"] = seed

        body = {
            "model": model,
            "input": {"messages": [{"role": "user", "content": content}]},
            "parameters": parameters,
        }

        logger.info(
            f"[WanxiangImageProvider] Generating via qwen-image sync: "
            f"model={model}, images={len(images)}, "
            f"size={parameters.get('size', 'auto')}"
        )

        async with httpx_module.AsyncClient(timeout=timeout) as client:
            create_url = f"{base_url}{_QWEN_SYNC_ENDPOINT}"
            resp = await client.post(create_url, headers=headers, json=body)
            resp.raise_for_status()
            result = resp.json()

            # Top-level error (code/message)
            raise_for_error(result, provider="qwen-image")

            # Sync response: output.choices[*].message.content[*].image
            image_url_out = None
            for choice in result.get("output", {}).get("choices", []):
                for item in choice.get("message", {}).get("content", []):
                    if item.get("image"):
                        image_url_out = item["image"]
                        break
                if image_url_out:
                    break
            if not image_url_out:
                raise ValueError(
                    f"qwen-image sync response has no image: {result}"
                )

            # Download image
            logger.info(
                f"[WanxiangImageProvider] Downloading image from {image_url_out}"
            )
            dl_resp = await client.get(image_url_out)
            dl_resp.raise_for_status()

            width, height = self._parse_dimensions(parameters.get("size") or "")
            usage = result.get("usage", {})

            return MediaGenResult(
                data=dl_resp.content,
                format="png",
                mime_type="image/png",
                width=width or usage.get("width"),
                height=height or usage.get("height"),
                metadata={
                    "model": model,
                    "size": parameters.get("size"),
                    "n": n,
                    "provider": "wanxiang",
                    "image_url": image_url_out,
                    "scenario": "i2i" if images else "t2i",
                    "input_image_count": len(images),
                },
            )

    def _build_headers(self, sync_mode: bool = False) -> dict[str, str]:
        """Build HTTP headers for DashScope API.

        sync_mode=True adds X-DashScope-Async (required by the legacy
        text2image/image-synthesis endpoint).
        """
        return build_headers(self.api_key, async_mode=sync_mode)

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
