"""Media Generation Provider Registry.

Singleton registry for media generation providers, following the same pattern
as derisk.agent.util.llm.provider.provider_registry.ProviderRegistry.

Provides runtime availability detection: providers are considered "available"
when their corresponding environment variables (API keys) are set.
"""

import logging
import os
from typing import Any, Callable, Dict, List, Optional, Type

from derisk.agent.util.media_gen.base import MediaGenProvider

logger = logging.getLogger(__name__)

MediaGenProviderFactory = Callable[..., MediaGenProvider]

# Provider-specific environment variable fallbacks.
# Each provider may have multiple env vars that can serve as its API key.
PROVIDER_ENV_FALLBACKS: Dict[str, List[str]] = {
    "openai": ["OPENAI_API_KEY"],
    "openai_video": ["OPENAI_API_KEY"],
    "wanxiang": ["DASHSCOPE_API_KEY", "DASHSCOPE_API_KEY_2", "ALIBABA_API_KEY"],
    "seedance": ["ARK_API_KEY", "VOLC_API_KEY", "VOLCENGINE_API_KEY"],
    "google": ["GOOGLE_API_KEY", "GEMINI_API_KEY", "GOOGLE_GENAI_API_KEY"],
}


class MediaGenProviderRegistry:
    """Singleton registry for media generation providers."""

    _instance: Optional["MediaGenProviderRegistry"] = None
    _providers: Dict[str, Type[MediaGenProvider]] = {}
    _factories: Dict[str, MediaGenProviderFactory] = {}
    _env_key_mappings: Dict[str, str] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @classmethod
    def register(
        cls,
        name: str,
        provider_class: Optional[Type[MediaGenProvider]] = None,
        factory: Optional[MediaGenProviderFactory] = None,
        env_key: Optional[str] = None,
    ):
        """Register a media generation provider.

        Can be used as a decorator or called directly.
        """

        def decorator(provider_cls: Type[MediaGenProvider]) -> Type[MediaGenProvider]:
            provider_name = name.lower()
            cls._providers[provider_name] = provider_cls
            if factory:
                cls._factories[provider_name] = factory
            if env_key:
                cls._env_key_mappings[provider_name] = env_key
            logger.info(f"Registered media gen provider: {provider_name}")
            return provider_cls

        if provider_class:
            return decorator(provider_class)
        return decorator

    @classmethod
    def get_provider_class(cls, name: str) -> Optional[Type[MediaGenProvider]]:
        return cls._providers.get(name.lower())

    @classmethod
    def get_env_key(cls, name: str) -> Optional[str]:
        return cls._env_key_mappings.get(name.lower())

    @classmethod
    def create_provider(
        cls,
        name: str,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        **kwargs: Any,
    ) -> Optional[MediaGenProvider]:
        """Create a provider instance by name."""
        provider_name = name.lower()

        factory = cls._factories.get(provider_name)
        if factory:
            return factory(api_key=api_key, base_url=base_url, **kwargs)

        provider_class = cls._providers.get(provider_name)
        if provider_class:
            return provider_class(api_key=api_key or "", base_url=base_url, **kwargs)

        return None

    @classmethod
    def list_providers(cls) -> Dict[str, Type[MediaGenProvider]]:
        return cls._providers.copy()

    @classmethod
    def has_provider(cls, name: str) -> bool:
        return name.lower() in cls._providers

    # ── Runtime availability detection ──────────────────────────────

    @classmethod
    def _check_api_key_available(cls, name: str) -> Optional[str]:
        """Check if a provider has a valid API key in env vars.

        Returns the API key if found, None otherwise.
        """
        provider_name = name.lower()

        # 1. Primary env var registered with the provider
        env_key = cls._env_key_mappings.get(provider_name)
        if env_key:
            val = os.environ.get(env_key)
            if val:
                return val

        # 2. Fallback env vars
        fallback_keys = PROVIDER_ENV_FALLBACKS.get(provider_name, [])
        for key in fallback_keys:
            val = os.environ.get(key)
            if val:
                return val

        # 3. Common fallbacks
        for key in ("MEDIA_GEN_API_KEY",):
            val = os.environ.get(key)
            if val:
                return val

        return None

    @classmethod
    def get_available_providers(cls) -> Dict[str, Dict[str, Any]]:
        """Return all providers that have valid API keys configured.

        Returns:
            Dict mapping provider_name -> {
                "api_key": str,
                "image_models": List[str],
                "video_models": List[str],
            }
        """
        result: Dict[str, Dict[str, Any]] = {}
        for name in cls._providers:
            api_key = cls._check_api_key_available(name)
            if not api_key:
                continue

            # Instantiate to query supported models (static, no network call)
            try:
                provider = cls.create_provider(name=name, api_key=api_key)
                if provider is None:
                    continue
                result[name] = {
                    "api_key": api_key,
                    "image_models": provider.supported_image_models(),
                    "video_models": provider.supported_video_models(),
                }
            except Exception as e:
                logger.warning(f"Failed to query provider '{name}': {e}")
        return result

    @classmethod
    def get_available_image_providers(cls) -> List[str]:
        """Return provider names that have API keys AND support image generation."""
        available = cls.get_available_providers()
        return [
            name for name, info in available.items()
            if info["image_models"]
        ]

    @classmethod
    def get_available_video_providers(cls) -> List[str]:
        """Return provider names that have API keys AND support video generation."""
        available = cls.get_available_providers()
        return [
            name for name, info in available.items()
            if info["video_models"]
        ]

    @classmethod
    def get_available_image_models(cls) -> List[Dict[str, str]]:
        """Return all available image models from providers with valid API keys.

        Returns:
            List of {"provider": str, "model": str} dicts.
        """
        models: List[Dict[str, str]] = []
        for name, info in cls.get_available_providers().items():
            for model in info["image_models"]:
                models.append({"provider": name, "model": model})
        return models

    @classmethod
    def get_available_video_models(cls) -> List[Dict[str, str]]:
        """Return all available video models from providers with valid API keys.

        Returns:
            List of {"provider": str, "model": str} dicts.
        """
        models: List[Dict[str, str]] = []
        for name, info in cls.get_available_providers().items():
            for model in info["video_models"]:
                models.append({"provider": name, "model": model})
        return models

    @classmethod
    def format_available_summary(cls) -> str:
        """Generate a human-readable summary of currently available providers/models.

        This is used to dynamically inject availability info into tool descriptions
        so the LLM knows which providers/models are actually usable.
        """
        available = cls.get_available_providers()
        if not available:
            return "⚠️ 当前没有配置任何多模态生成服务的 API Key。\n请设置以下环境变量之一：OPENAI_API_KEY, DASHSCOPE_API_KEY, ARK_API_KEY, GOOGLE_API_KEY"

        lines = ["**当前可用的多模态生成服务：**\n"]
        for name, info in sorted(available.items()):
            img_models = info["image_models"]
            vid_models = info["video_models"]
            if img_models:
                lines.append(f"- `{name}` (图片): {', '.join(img_models)}")
            if vid_models:
                lines.append(f"- `{name}` (视频): {', '.join(vid_models)}")

        return "\n".join(lines)
