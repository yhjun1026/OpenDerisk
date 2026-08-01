"""Volcano Engine Seedance (豆包视频生成) Video Generation Provider.

Implements video generation via the Volcano Engine Ark API, supporting:
- doubao-seedance-2-0-250428 (Seedance 2.0, newest)
- doubao-seedance-1-5-pro-251215 (Seedance 1.5 Pro)
- doubao-seedance-1-0-pro-250428 (Seedance 1.0 Pro)
- doubao-seedance-1-0-pro-fast-250428 (Seedance 1.0 Pro Fast)

API docs: https://www.volcengine.com/docs/82379/1520757
"""

import asyncio
import logging
from typing import Any, List, Optional

from derisk.agent.util.media_gen.base import MediaGenProvider, MediaGenResult
from derisk.agent.util.media_gen.provider_registry import MediaGenProviderRegistry

logger = logging.getLogger(__name__)

# All supported Seedance models
_SUPPORTED_MODELS = {
    "doubao-seedance-2-0-250428",
    "doubao-seedance-1-5-pro-251215",
    "doubao-seedance-1-0-pro-250428",
    "doubao-seedance-1-0-pro-fast-250428",
}

# Default API endpoints
_DEFAULT_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"
_CREATE_TASK_ENDPOINT = "/contents/generations/tasks"
_QUERY_TASK_ENDPOINT = "/contents/generations/tasks/{task_id}"

# Supported resolutions
_SUPPORTED_RESOLUTIONS = {"480p", "720p", "1080p", "4k"}

# Supported aspect ratios
_SUPPORTED_RATIOS = {"16:9", "4:3", "1:1", "3:4", "9:16", "21:9", "adaptive"}


@MediaGenProviderRegistry.register(name="seedance", env_key="ARK_API_KEY")
class SeedanceVideoProvider(MediaGenProvider):
    """Volcano Engine Seedance (豆包) video generation provider.

    Uses the Ark API with async task pattern: submit -> poll -> download.
    Supports text-to-video and image-to-video generation.
    """

    def supported_image_models(self) -> List[str]:
        return []

    def supported_video_models(self) -> List[str]:
        return sorted(_SUPPORTED_MODELS)

    async def generate_image(
        self,
        prompt: str,
        model: str = "",
        **kwargs: Any,
    ) -> MediaGenResult:
        raise NotImplementedError(
            "Seedance video provider does not support image generation"
        )

    async def generate_video(
        self,
        prompt: str,
        model: str = "doubao-seedance-1-0-pro-250428",
        **kwargs: Any,
    ) -> MediaGenResult:
        """Generate a video using Volcano Engine Seedance API.

        Args:
            prompt: Text description of the video (supports Chinese & English).
            model: Model to use (doubao-seedance-2-0-250428, doubao-seedance-1-5-pro-251215, etc.).
            **kwargs: Additional params:
                - duration: Video duration in seconds (default 5, range 1-15).
                - resolution: "480p", "720p", "1080p", "4k" (default "720p").
                - aspect_ratio: "16:9", "4:3", "1:1", "3:4", "9:16", "21:9", "adaptive"
                  (default "16:9").
                - seed: Random seed for reproducibility.
                - watermark: Whether to add watermark (default False).
                - camera_fixed: Whether to fix camera (default False).
                - generate_audio: Whether to generate audio (default True for 2.0/1.5 Pro).
                - image_url: First frame image URL for image-to-video generation.
                - image_url_last: Last frame image URL for first-last-frame video generation.
                - timeout: Max wait time in seconds (default 600).
        """
        try:
            import httpx
        except ImportError:
            raise ImportError(
                "httpx package is required for Seedance video generation. "
                "Install with: pip install httpx"
            )

        timeout = kwargs.get("timeout", 600)
        base_url = self.base_url or _DEFAULT_BASE_URL

        duration = kwargs.get("duration", 5)
        resolution = kwargs.get("resolution", "720p")
        aspect_ratio = kwargs.get("aspect_ratio", "16:9")
        seed = kwargs.get("seed")
        watermark = kwargs.get("watermark", False)
        camera_fixed = kwargs.get("camera_fixed", False)
        generate_audio = kwargs.get("generate_audio")
        image_url = kwargs.get("image_url")
        image_url_last = kwargs.get("image_url_last")

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        # Build content array
        content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]

        # Add first frame image if provided (image-to-video)
        if image_url:
            image_obj: dict[str, Any] = {
                "type": "image_url",
                "image_url": {"url": image_url},
            }
            if image_url_last:
                # First + last frame mode
                image_obj["role"] = "first_frame"
                content.append(image_obj)
                content.append(
                    {
                        "type": "image_url",
                        "image_url": {"url": image_url_last},
                        "role": "last_frame",
                    }
                )
            else:
                # First frame only mode
                image_obj["role"] = "first_frame"
                content.append(image_obj)

        # Build request body
        body: dict[str, Any] = {
            "model": model,
            "content": content,
            "resolution": resolution,
            "ratio": aspect_ratio,
            "duration": duration,
            "watermark": watermark,
            "camera_fixed": camera_fixed,
        }

        # Optional parameters
        if seed is not None:
            body["seed"] = seed
        if generate_audio is not None:
            body["generate_audio"] = generate_audio

        logger.info(
            f"[SeedanceVideoProvider] Submitting video job: model={model}, "
            f"duration={duration}s, resolution={resolution}, ratio={aspect_ratio}, "
            f"image_to_video={'yes' if image_url else 'no'}"
        )

        async with httpx.AsyncClient(timeout=timeout) as client:
            # Step 1: Submit generation task
            create_url = f"{base_url}{_CREATE_TASK_ENDPOINT}"
            submit_resp = await client.post(create_url, headers=headers, json=body)
            submit_resp.raise_for_status()
            job = submit_resp.json()

            task_id = job.get("id")
            if not task_id:
                raise ValueError(f"Seedance API returned no task ID: {job}")

            logger.info(f"[SeedanceVideoProvider] Task created: {task_id}")

            # Step 2: Poll until complete
            video_url = await self._poll_task(
                client, base_url, task_id, timeout
            )

            # Step 3: Download video
            logger.info(
                f"[SeedanceVideoProvider] Downloading video from {video_url}"
            )
            dl_resp = await client.get(video_url)
            dl_resp.raise_for_status()

            metadata: dict[str, Any] = {
                "model": model,
                "resolution": resolution,
                "aspect_ratio": aspect_ratio,
                "duration": duration,
                "task_id": task_id,
                "provider": "seedance",
                "video_url": video_url,
            }
            if seed is not None:
                metadata["seed"] = seed
            if image_url:
                metadata["image_to_video"] = True

            return MediaGenResult(
                data=dl_resp.content,
                format="mp4",
                mime_type="video/mp4",
                duration_seconds=float(duration),
                metadata=metadata,
            )

    async def _poll_task(
        self,
        client: Any,
        base_url: str,
        task_id: str,
        timeout: int,
    ) -> str:
        """Poll Seedance task until completion, return video URL.

        Args:
            client: httpx.AsyncClient instance.
            base_url: Ark API base URL.
            task_id: Task ID to poll.
            timeout: Maximum wait time in seconds.

        Returns:
            Video URL string.
        """
        query_url = f"{base_url}{_QUERY_TASK_ENDPOINT.format(task_id=task_id)}"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
        }

        poll_interval = 10  # seconds (video generation takes longer)
        elapsed = 0

        while elapsed < timeout:
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

            resp = await client.get(query_url, headers=headers)
            resp.raise_for_status()
            status_data = resp.json()

            status = status_data.get("status", "")

            if status == "succeeded":
                # Extract video URL from content.video_url.url
                content_list = status_data.get("content", [])
                for item in content_list:
                    if item.get("type") == "video_url":
                        video_url_obj = item.get("video_url", {})
                        url = video_url_obj.get("url")
                        if url:
                            return url

                # Fallback: try output field
                output = status_data.get("output", {})
                if isinstance(output, dict):
                    url = output.get("url")
                    if url:
                        return url

                raise ValueError(
                    f"Task succeeded but no video URL found: {status_data}"
                )

            elif status in ("failed", "cancelled", "expired"):
                error = status_data.get("error", {})
                error_msg = ""
                if isinstance(error, dict):
                    error_msg = error.get("message", "")
                if not error_msg:
                    error_msg = status_data.get("message", "Unknown error")
                raise RuntimeError(
                    f"Seedance video generation failed (status={status}): {error_msg}"
                )

            logger.debug(
                f"[SeedanceVideoProvider] Task {task_id} status: {status} "
                f"({elapsed}s elapsed)"
            )

        raise TimeoutError(
            f"Seedance video generation timed out after {timeout}s "
            f"(task_id={task_id})"
        )
