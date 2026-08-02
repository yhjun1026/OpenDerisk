"""Google Banana (Nano Banana) Image Generation Provider.

Implements image generation and editing via Google Gemini 2.5 Flash Image API.

The model "gemini-2.5-flash-image-preview" (code-named "Nano Banana") is Google's
multimodal image generation model released in August 2025. It supports:
- Text-to-image generation
- Image editing (with reference image)
- Multi-image composition
- Multilingual prompts (Chinese, English, etc.)

API documentation:
- Google GenAI SDK: https://googleapis.github.io/python-genai/
- Model: models/gemini-2.5-flash-image-preview
"""

import base64
import io
import logging
from typing import Any, Dict, List, Optional

from derisk.agent.util.media_gen.base import MediaGenProvider, MediaGenResult
from derisk.agent.util.media_gen.provider_registry import MediaGenProviderRegistry

logger = logging.getLogger(__name__)

# Model names are free-form (protocol-based routing); passed through to the
# Gemini API.

# Google's default endpoint
_DEFAULT_BASE_URL = "https://generativelanguage.googleapis.com"


@MediaGenProviderRegistry.register(protocol="google_image", env_key="GOOGLE_API_KEY")
class GoogleBananaProvider(MediaGenProvider):
    """Google Gemini 2.5 Flash Image (Nano Banana) generation provider.

    Supports:
    - Text-to-image generation
    - Image editing with reference images (via image_url parameter)
    - Multilingual prompts
    Model name is free-form (passed through to the Gemini API).
    """

    def supported_image_models(self) -> List[str]:
        return []

    def supported_video_models(self) -> List[str]:
        return []

    async def generate_image(
        self,
        prompt: str,
        model: str = "gemini-2.5-flash-image-preview",
        **kwargs: Any,
    ) -> MediaGenResult:
        """Generate an image using Google Gemini 2.5 Flash Image API.

        Args:
            prompt: Text description of the image (supports Chinese and English).
            model: Model name (default: gemini-2.5-flash-image-preview).
            **kwargs: Additional params:
                - image_url: Reference image URL for editing mode (optional).
                  Supports public URLs and base64 data URIs.
                - size: Not directly supported by Gemini, ignored.
                - n: Number of images (Gemini generates 1 per call).
                - seed: Not supported by Gemini API.
        """
        image_url = kwargs.get("image_url")

        try:
            result = await self._generate_via_genai_sdk(prompt, model, image_url, kwargs)
        except ImportError:
            logger.info("[GoogleBananaProvider] google-genai not installed, trying google-generativeai")
            result = await self._generate_via_generativeai(prompt, model, image_url, kwargs)

        return result

    async def _generate_via_genai_sdk(
        self,
        prompt: str,
        model: str,
        image_url: Optional[str],
        kwargs: Dict[str, Any],
    ) -> MediaGenResult:
        """Generate image using the google-genai SDK (preferred)."""
        try:
            from google import genai
            from google.genai import types
        except ImportError:
            raise ImportError(
                "google-genai package is required for Google Banana image generation. "
                "Install with: pip install google-genai"
            )

        # Build client
        client_kwargs: dict[str, Any] = {"api_key": self.api_key}
        if self.base_url:
            client_kwargs["http_options"] = types.HttpOptions(base_url=self.base_url)
        client = genai.Client(**client_kwargs)

        # Build contents
        contents: list[Any] = [prompt]

        # Add reference image if provided (image editing mode)
        if image_url:
            ref_image_bytes = self._fetch_image_bytes(image_url)
            if ref_image_bytes:
                # Determine mime type from URL or default to png
                mime_type = "image/png"
                if image_url.startswith("data:"):
                    # Parse mime from data URI
                    header = image_url.split(",")[0]
                    if ";" in header and "/" in header:
                        mime_type = header.split(":")[1].split(";")[0]
                contents.append(types.Part.from_bytes(data=ref_image_bytes, mime_type=mime_type))

        logger.info(
            f"[GoogleBananaProvider] Generating image: model={model}, "
            f"prompt_len={len(prompt)}, has_ref_image={bool(image_url)}"
        )

        # Generate
        config = types.GenerateContentConfig(
            response_modalities=["IMAGE", "TEXT"],
        )

        response = await client.aio.models.generate_content(
            model=model,
            contents=contents,
            config=config,
        )

        # Extract image from response
        image_bytes = None
        mime_type = "image/png"
        revised_prompt = None

        if response.candidates:
            for candidate in response.candidates:
                if candidate.content and candidate.content.parts:
                    for part in candidate.content.parts:
                        if part.inline_data and part.inline_data.data:
                            image_bytes = part.inline_data.data
                            if part.inline_data.mime_type:
                                mime_type = part.inline_data.mime_type
                            break
                        if part.text and not revised_prompt:
                            revised_prompt = part.text
                    if image_bytes:
                        break

        if not image_bytes:
            raise ValueError("Google Gemini API returned no image data")

        # Determine format from mime_type
        fmt = mime_type.split("/")[-1] if "/" in mime_type else "png"
        if fmt == "jpeg":
            fmt = "jpg"

        metadata: dict[str, Any] = {
            "model": model,
            "provider": "google",
            "provider_display_name": "Google Nano Banana",
            "prompt": prompt[:200],
        }
        if revised_prompt:
            metadata["revised_prompt"] = revised_prompt
        if image_url:
            metadata["edit_mode"] = True

        return MediaGenResult(
            data=image_bytes,
            format=fmt,
            mime_type=mime_type,
            metadata=metadata,
        )

    async def _generate_via_generativeai(
        self,
        prompt: str,
        model: str,
        image_url: Optional[str],
        kwargs: Dict[str, Any],
    ) -> MediaGenResult:
        """Fallback: Generate image using the google-generativeai SDK."""
        try:
            import google.generativeai as genai
        except ImportError:
            raise ImportError(
                "Either google-genai or google-generativeai package is required. "
                "Install with: pip install google-genai"
            )

        genai.configure(api_key=self.api_key)
        gm = genai.GenerativeModel(model)

        contents: list[Any] = [prompt]

        if image_url:
            ref_image_bytes = self._fetch_image_bytes(image_url)
            if ref_image_bytes:
                import PIL.Image as PILImage
                img = PILImage.open(io.BytesIO(ref_image_bytes))
                contents.append(img)

        logger.info(
            f"[GoogleBananaProvider] Generating via generativeai: model={model}"
        )

        response = gm.generate_content(
            contents,
            generation_config=genai.GenerationConfig(
                response_modalities=["IMAGE", "TEXT"],
            ),
        )

        image_bytes = None
        mime_type = "image/png"
        revised_prompt = None

        for candidate in response.candidates:
            for part in candidate.content.parts:
                if hasattr(part, "inline_data") and part.inline_data:
                    image_bytes = part.inline_data.data
                    if hasattr(part.inline_data, "mime_type") and part.inline_data.mime_type:
                        mime_type = part.inline_data.mime_type
                    break
                if hasattr(part, "text") and part.text and not revised_prompt:
                    revised_prompt = part.text
            if image_bytes:
                break

        if not image_bytes:
            raise ValueError("Google Gemini API returned no image data")

        fmt = mime_type.split("/")[-1] if "/" in mime_type else "png"
        if fmt == "jpeg":
            fmt = "jpg"

        metadata: dict[str, Any] = {
            "model": model,
            "provider": "google",
            "provider_display_name": "Google Nano Banana",
            "prompt": prompt[:200],
        }
        if revised_prompt:
            metadata["revised_prompt"] = revised_prompt
        if image_url:
            metadata["edit_mode"] = True

        return MediaGenResult(
            data=image_bytes,
            format=fmt,
            mime_type=mime_type,
            metadata=metadata,
        )

    def _fetch_image_bytes(self, url: str) -> Optional[bytes]:
        """Fetch image bytes from URL or data URI."""
        if url.startswith("data:"):
            # Data URI: data:image/png;base64,xxxx
            try:
                header, data = url.split(",", 1)
                return base64.b64decode(data)
            except Exception as e:
                logger.warning(f"[GoogleBananaProvider] Failed to decode data URI: {e}")
                return None

        # Public URL
        try:
            import urllib.request

            req = urllib.request.Request(url, headers={"User-Agent": "OpenDerisk/1.0"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.read()
        except Exception as e:
            logger.warning(f"[GoogleBananaProvider] Failed to fetch image from {url}: {e}")
            return None

    async def generate_video(
        self,
        prompt: str,
        model: str = "",
        **kwargs: Any,
    ) -> MediaGenResult:
        raise NotImplementedError(
            "Google Banana provider does not support video generation. "
            "Use 'seedance' or 'openai_video' for video."
        )
