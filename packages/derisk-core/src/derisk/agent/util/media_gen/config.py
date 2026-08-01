"""Media Generation configuration model."""

from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class MediaGenConfig(BaseModel):
    """Configuration for media generation providers.

    Supports multiple providers:
    - Image: openai (DALL-E), wanxiang (通义万相), google (Nano Banana)
    - Video: openai_video (Sora), seedance (豆包 Seedance)
    """

    provider: str = Field(default="openai", description="Default provider name")
    api_key: Optional[str] = Field(default=None, description="Provider API key")
    base_url: Optional[str] = Field(default=None, description="Custom API endpoint")
    default_image_model: str = Field(
        default="dall-e-3",
        description="Default image model (dall-e-3, wan2.6-t2i, gemini-2.5-flash-image-preview, etc.)",
    )
    default_video_model: str = Field(
        default="sora",
        description="Default video model (sora, doubao-seedance-1-0-pro-250428, etc.)",
    )
    max_concurrent_requests: int = Field(default=3, description="Max concurrent generation requests")
    extra_kwargs: Dict[str, Any] = Field(default_factory=dict, description="Provider-specific kwargs")
