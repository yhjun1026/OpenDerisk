"""Media Generation Provider module.

Provides pluggable providers for image/video generation:
- OpenAI DALL-E (image) and Sora (video)
- Alibaba Cloud Wanxiang / 通义万相 (image)
- Volcano Engine Seedance / 豆包 (video)
- Google Nano Banana / Gemini 2.5 Flash Image (image)
"""

from derisk.agent.util.media_gen.base import MediaGenProvider, MediaGenResult
from derisk.agent.util.media_gen.config import MediaGenConfig
from derisk.agent.util.media_gen.provider_registry import MediaGenProviderRegistry

# Auto-register built-in providers on import
from derisk.agent.util.media_gen import openai_image_provider  # noqa: F401
from derisk.agent.util.media_gen import openai_video_provider  # noqa: F401
from derisk.agent.util.media_gen import wanxiang_image_provider  # noqa: F401
from derisk.agent.util.media_gen import seedance_video_provider  # noqa: F401
from derisk.agent.util.media_gen import google_banana_provider  # noqa: F401

__all__ = [
    "MediaGenProvider",
    "MediaGenResult",
    "MediaGenConfig",
    "MediaGenProviderRegistry",
]
