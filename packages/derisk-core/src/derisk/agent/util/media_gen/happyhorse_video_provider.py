"""Alibaba Cloud HappyHorse (通义万相视频) Video Generation Provider.

Implements video generation via the DashScope API, supporting three scenarios
routed by model name suffix:
- happyhorse-1.1-t2v / happyhorse-1.0-t2v  (text-to-video)
- happyhorse-1.1-i2v / happyhorse-1.0-i2v  (image-to-video, first frame)
- happyhorse-1.1-r2v / happyhorse-1.0-r2v  (reference-to-video, 1~9 reference images)

All scenarios share the same endpoint; the difference is `input.media`.
Uses the DashScope async task pattern: submit -> poll -> download.

API docs:
- t2v: https://help.aliyun.com/zh/model-studio/happyhorse-text-to-video-api-reference
- i2v: https://help.aliyun.com/zh/model-studio/happyhorse-image-to-video-api-reference
- r2v: https://help.aliyun.com/zh/model-studio/happyhorse-reference-to-video-api-reference
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

# Model names are free-form (protocol-based routing). Scenario is derived from
# the model-name suffix (-t2v / -i2v / -r2v), so future versions work without
# code changes.

# Default API endpoints (DashScope generic domain; workspace-specific maas
# domain can be supplied via base_url for better performance/stability)
_DEFAULT_BASE_URL = "https://dashscope.aliyuncs.com"
_CREATE_TASK_ENDPOINT = "/api/v1/services/aigc/video-generation/video-synthesis"

# Supported resolutions (HappyHorse uses uppercase, no 4k)
_SUPPORTED_RESOLUTIONS = {"480P", "720P", "1080P"}

# Supported aspect ratios for t2v / r2v (i2v follows the first frame)
_SUPPORTED_RATIOS = {
    "16:9", "9:16", "1:1", "4:3", "3:4", "4:5", "5:4", "9:21", "21:9",
}


def _scenario_of(model: str) -> str:
    """Return the scenario tag (t2v / i2v / r2v) from a model name."""
    name = model.lower()
    if name.endswith("-t2v"):
        return "t2v"
    if name.endswith("-i2v"):
        return "i2v"
    if name.endswith("-r2v"):
        return "r2v"
    return ""


def _extract_video_url(data: dict) -> str:
    """Extract video_url from a SUCCEEDED DashScope task response."""
    url = data.get("output", {}).get("video_url")
    if not url:
        raise ValueError(f"Task succeeded but no video_url found: {data}")
    return url


@MediaGenProviderRegistry.register(protocol="dashscope_video", env_key="DASHSCOPE_API_KEY")
class HappyHorseVideoProvider(MediaGenProvider):
    """Alibaba Cloud HappyHorse video generation provider.

    Uses the DashScope API with async task pattern: submit -> poll -> download.
    Supports text-to-video, image-to-video (first frame) and
    reference-to-video (multiple reference images). Model name is free-form;
    scenario is routed by the model-name suffix (-t2v / -i2v / -r2v).
    """

    def supported_image_models(self) -> List[str]:
        return []

    def supported_video_models(self) -> List[str]:
        return []

    async def generate_image(
        self,
        prompt: str,
        model: str = "",
        **kwargs: Any,
    ) -> MediaGenResult:
        raise NotImplementedError(
            "HappyHorse video provider does not support image generation"
        )

    async def generate_video(
        self,
        prompt: str,
        model: str = "happyhorse-1.1-t2v",
        **kwargs: Any,
    ) -> MediaGenResult:
        """Generate a video using Alibaba Cloud HappyHorse API.

        Args:
            prompt: Text description of the video (supports Chinese & English).
            model: Model to use (happyhorse-1.1-t2v / -i2v / -r2v, or 1.0 variants).
            **kwargs: Additional params:
                - duration: Video duration in seconds (default 5, range 3-15).
                - resolution: "480p", "720p", "1080p" (default "1080p").
                  Case-insensitive; normalized to HappyHorse's uppercase form.
                - aspect_ratio: "16:9", "9:16", "1:1", "4:3", "3:4", "4:5",
                  "5:4", "9:21", "21:9" (default "16:9"). Only for t2v/r2v;
                  i2v follows the first frame and ignores this param.
                - seed: Random seed for reproducibility.
                - watermark: Whether to add "Happy Horse" watermark (default False).
                  Note: HappyHorse's own default is True; we pass False explicitly
                  to keep the tool's "no watermark by default" semantics.
                - image_url: First frame image URL for i2v (required for i2v).
                  Supports public URL and Base64 (data:image/xxx;base64,...).
                - reference_images: List of 1~9 reference image URLs for r2v
                  (required for r2v). Use [Image 1]/[Image 2] in the prompt to
                  refer to them.
                - timeout: Max wait time in seconds (default 600).
        """
        try:
            import httpx
        except ImportError:
            raise ImportError(
                "httpx package is required for HappyHorse video generation. "
                "Install with: pip install httpx"
            )

        scenario = _scenario_of(model)
        if not scenario:
            raise ValueError(
                f"Unknown HappyHorse model '{model}'. "
                f"Supported: {sorted(_SUPPORTED_MODELS)}"
            )

        timeout = kwargs.get("timeout", 600)
        base_url = self.base_url or _DEFAULT_BASE_URL

        duration = kwargs.get("duration", 5)
        resolution = self._normalize_resolution(kwargs.get("resolution", "1080p"))
        aspect_ratio = kwargs.get("aspect_ratio", "16:9")
        seed = kwargs.get("seed")
        watermark = kwargs.get("watermark", False)
        image_url = kwargs.get("image_url")
        reference_images = kwargs.get("reference_images")

        # Validate duration (HappyHorse range is 3-15)
        if not isinstance(duration, int) or duration < 3 or duration > 15:
            raise ValueError(
                f"HappyHorse duration must be an integer in [3, 15], got {duration}"
            )

        # Build input.media based on scenario
        media = self._build_media(scenario, image_url, reference_images)

        # Build parameters: ratio only applies to t2v / r2v (i2v follows first frame)
        parameters: dict[str, Any] = {
            "resolution": resolution,
            "duration": duration,
            "watermark": watermark,
        }
        if scenario in ("t2v", "r2v"):
            if aspect_ratio not in _SUPPORTED_RATIOS:
                raise ValueError(
                    f"Unsupported aspect_ratio '{aspect_ratio}' for HappyHorse "
                    f"{scenario}. Supported: {sorted(_SUPPORTED_RATIOS)}"
                )
            parameters["ratio"] = aspect_ratio
        if seed is not None:
            parameters["seed"] = seed

        body: dict[str, Any] = {
            "model": model,
            "input": {"prompt": prompt},
            "parameters": parameters,
        }
        if media:
            body["input"]["media"] = media

        headers = build_headers(self.api_key, async_mode=True)

        logger.info(
            f"[HappyHorseVideoProvider] Submitting {scenario} job: model={model}, "
            f"duration={duration}s, resolution={resolution}, "
            f"ratio={parameters.get('ratio', 'n/a')}, "
            f"media_count={len(media) if media else 0}"
        )

        async with httpx.AsyncClient(timeout=timeout) as client:
            # Step 1: Submit generation task
            create_url = f"{base_url}{_CREATE_TASK_ENDPOINT}"
            submit_resp = await client.post(create_url, headers=headers, json=body)
            submit_resp.raise_for_status()
            result = submit_resp.json()

            # Error response: top-level code/message
            raise_for_error(result, provider="happyhorse")

            task_id = result.get("output", {}).get("task_id")
            if not task_id:
                raise ValueError(
                    f"HappyHorse API returned no task_id: {result}"
                )

            logger.info(f"[HappyHorseVideoProvider] Task created: {task_id}")

            # Step 2: Poll until complete
            video_url = await poll_dashscope_task(
                client, base_url, task_id, self.api_key, timeout,
                extract_url=_extract_video_url,
                poll_interval=15,
                provider="happyhorse",
            )

            # Step 3: Download video
            logger.info(
                f"[HappyHorseVideoProvider] Downloading video from {video_url}"
            )
            dl_resp = await client.get(video_url)
            dl_resp.raise_for_status()

            metadata: dict[str, Any] = {
                "model": model,
                "scenario": scenario,
                "resolution": resolution,
                "duration": duration,
                "task_id": task_id,
                "provider": "happyhorse",
                "video_url": video_url,
            }
            if scenario in ("t2v", "r2v"):
                metadata["aspect_ratio"] = aspect_ratio
            if seed is not None:
                metadata["seed"] = seed
            if scenario == "i2v":
                metadata["image_to_video"] = True
            elif scenario == "r2v":
                metadata["reference_image_count"] = len(media)

            return MediaGenResult(
                data=dl_resp.content,
                format="mp4",
                mime_type="video/mp4",
                duration_seconds=float(duration),
                metadata=metadata,
            )

    def _build_media(
        self,
        scenario: str,
        image_url: Optional[str],
        reference_images: Optional[List[str]],
    ) -> List[dict[str, Any]]:
        """Build input.media array based on the scenario."""
        if scenario == "t2v":
            return []

        if scenario == "i2v":
            if not image_url:
                raise ValueError(
                    "image_url is required for HappyHorse image-to-video (i2v)"
                )
            return [{"type": "first_frame", "url": image_url}]

        # r2v: reference images
        if not reference_images:
            raise ValueError(
                "reference_images is required for HappyHorse "
                "reference-to-video (r2v)"
            )
        if not isinstance(reference_images, (list, tuple)):
            raise ValueError("reference_images must be a list of URL strings")
        if len(reference_images) < 1 or len(reference_images) > 9:
            raise ValueError(
                f"HappyHorse r2v requires 1~9 reference images, "
                f"got {len(reference_images)}"
            )
        return [
            {"type": "reference_image", "url": url}
            for url in reference_images
            if url
        ]

    def _normalize_resolution(self, resolution: str) -> str:
        """Normalize resolution to HappyHorse's uppercase form (e.g. 720p -> 720P)."""
        normalized = resolution.strip().upper()
        if normalized not in _SUPPORTED_RESOLUTIONS:
            raise ValueError(
                f"Unsupported resolution '{resolution}' for HappyHorse. "
                f"Supported: {sorted(_SUPPORTED_RESOLUTIONS)}"
            )
        return normalized
