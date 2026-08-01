"""Media Generation Tools.

Agent tools for generating images and videos using AI models.
Integrates with MediaGenProviderRegistry for multi-provider support
and AgentFileSystem/d-attach for file delivery.

Supported providers:
- Image: openai (DALL-E 3/2, gpt-image-1), wanxiang (通义万相 wan2.6/wanx2.1/wanx-v1), google (Nano Banana)
- Video: openai_video (Sora), seedance (豆包 Seedance 2.0/1.5 Pro/1.0 Pro)

Tool descriptions are dynamically augmented with currently available providers/models
based on which API keys are configured in environment variables.
"""

import logging
import os
import uuid
from typing import Any, Dict, List, Optional

from derisk.agent.tools.base import ToolBase, ToolCategory, ToolRiskLevel, ToolSource
from derisk.agent.tools.context import ToolContext
from derisk.agent.tools.metadata import ToolMetadata
from derisk.agent.tools.result import Artifact, ToolResult

logger = logging.getLogger(__name__)

_GENERATE_IMAGE_PROMPT = """使用 AI 模型生成图片。

**支持的 Provider 和模型：**

| Provider | 模型 | 说明 |
|----------|------|------|
| openai | dall-e-3, dall-e-2, gpt-image-1 | OpenAI DALL-E 系列 |
| wanxiang | wan2.6-t2i, wan2.5-t2i-preview, wan2.2-t2i-flash, wan2.2-t2i-plus, wanx2.1-t2i-turbo, wanx2.1-t2i-plus, wanx2.0-t2i-turbo, wanx-v1 | 阿里云通义万相 |
| google | gemini-2.5-flash-image-preview, gemini-2.5-flash-image | Google Nano Banana (支持图片生成和编辑) |

**使用场景：**
- 根据文字描述生成图片
- 生成数据可视化、插图、概念图等
- Google Nano Banana 还支持图片编辑 (通过 image_url 传入参考图)
- 生成的图片会自动保存并交付给用户

**推荐用法：**
```
# 使用 OpenAI DALL-E 3 生成图片
generate_image(prompt="一只在星空下弹吉他的猫，赛博朋克风格", provider="openai", model="dall-e-3", size="1024x1024")

# 使用阿里云通义万相生成图片 (支持中英文)
generate_image(prompt="一只坐着的橘黄色的猫，表情愉悦，活泼可爱", provider="wanxiang", model="wan2.6-t2i", size="1280*1280")

# 使用通义万相极速版 (更快的生成速度)
generate_image(prompt="产品界面设计图", provider="wanxiang", model="wanx2.1-t2i-turbo", size="1024*1024")

# 使用 Google Nano Banana 生成图片 (支持中英文)
generate_image(prompt="一只在星空下弹吉他的猫，赛博朋克风格", provider="google", model="gemini-2.5-flash-image-preview")

# 使用 Google Nano Banana 编辑图片 (传入参考图)
generate_image(prompt="把背景改成日落场景", provider="google", model="gemini-2.5-flash-image-preview", image_url="https://example.com/original.jpg")

# 使用反向提示词 (排除不想要的内容)
generate_image(prompt="一座美丽的城市夜景", provider="wanxiang", model="wan2.6-t2i", negative_prompt="低分辨率，模糊，变形")
```

**注意事项：**
- 生成图片需要消耗 API 配额，请合理使用
- 图片生成通常需要 10-60 秒 (通义万相异步任务可能需要更长时间)
- 生成的图片会自动上传到存储并生成交付链接
- OpenAI 需设置 OPENAI_API_KEY 环境变量
- 通义万相需设置 DASHSCOPE_API_KEY 环境变量
- Google Nano Banana 需设置 GOOGLE_API_KEY 环境变量
"""

_GENERATE_VIDEO_PROMPT = """使用 AI 模型生成视频。

**支持的 Provider 和模型：**

| Provider | 模型 | 说明 |
|----------|------|------|
| openai_video | sora | OpenAI Sora |
| seedance | doubao-seedance-2-0-250428, doubao-seedance-1-5-pro-251215, doubao-seedance-1-0-pro-250428, doubao-seedance-1-0-pro-fast-250428 | 火山引擎豆包 Seedance |

**使用场景：**
- 根据文字描述生成短视频 (文生视频)
- 根据首帧图片 + 文字描述生成视频 (图生视频)
- 根据首帧 + 尾帧图片生成视频 (首尾帧生视频，仅 Seedance)
- 生成产品演示、概念视频等

**推荐用法：**
```
# 使用 OpenAI Sora 生成视频
generate_video(prompt="日落时分海浪拍打沙滩的慢镜头", provider="openai_video", model="sora", duration=5)

# 使用火山引擎 Seedance 文生视频
generate_video(prompt="一只小猫对着镜头打哈欠", provider="seedance", model="doubao-seedance-1-0-pro-250428", duration=5, resolution="720p")

# 使用 Seedance 图生视频 (首帧图片)
generate_video(prompt="镜头缓慢推进，女孩转头微笑", provider="seedance", model="doubao-seedance-2-0-250428", image_url="https://example.com/first_frame.jpg", duration=5)

# 使用 Seedance 首尾帧生视频
generate_video(prompt="从白天过渡到夜晚", provider="seedance", model="doubao-seedance-1-5-pro-251215", image_url="https://example.com/day.jpg", image_url_last="https://example.com/night.jpg", duration=5)

# 生成无声视频
generate_video(prompt="城市夜景延时摄影", provider="seedance", model="doubao-seedance-2-0-250428", generate_audio=false)
```

**注意事项：**
- 视频生成需要较长时间 (通常 1-10 分钟)
- 视频生成消耗较多 API 配额
- 生成的视频会自动上传到存储并生成交付链接
- OpenAI 需设置 OPENAI_API_KEY 环境变量
- 火山引擎需设置 ARK_API_KEY 环境变量
- image_url 支持公网 URL 和 Base64 编码 (data:image/xxx;base64,...)
"""


def _get_agent_file_system(context: Optional[ToolContext]) -> Any:
    """Get AgentFileSystem from tool context."""
    if context is None:
        return None

    if isinstance(context, dict):
        # From config dict
        afs = context.get("agent_file_system")
        if afs:
            return afs
        config = context.get("config", {})
        afs = config.get("agent_file_system")
        if afs:
            return afs
        # From sandbox_manager
        sm = config.get("sandbox_manager") or context.get("sandbox_manager")
        if sm and hasattr(sm, "agent_file_system"):
            return sm.agent_file_system
        # From sandbox_client
        sc = config.get("sandbox_client") or context.get("sandbox_client")
        if sc and hasattr(sc, "agent_file_system"):
            return sc.agent_file_system
        return None

    # ToolContext object
    afs = context.config.get("agent_file_system")
    if afs:
        return afs
    afs = context.get_resource("agent_file_system")
    if afs:
        return afs
    # From sandbox_manager
    sm = context.config.get("sandbox_manager")
    if sm and hasattr(sm, "agent_file_system"):
        return sm.agent_file_system
    # From sandbox_client
    sc = context.config.get("sandbox_client")
    if sc and hasattr(sc, "agent_file_system"):
        return sc.agent_file_system
    return None


def _resolve_api_key(provider_name: str, context: Optional[ToolContext]) -> Optional[str]:
    """Resolve API key from context config or environment variables."""
    from derisk.agent.util.media_gen.provider_registry import (
        MediaGenProviderRegistry,
        PROVIDER_ENV_FALLBACKS,
    )

    # 1. From context config
    if context:
        config = context.config if not isinstance(context, dict) else context
        media_gen_config = config.get("media_gen_config") if isinstance(config, dict) else config.get("media_gen_config")
        if media_gen_config:
            if hasattr(media_gen_config, "api_key") and media_gen_config.api_key:
                return media_gen_config.api_key
            if isinstance(media_gen_config, dict) and media_gen_config.get("api_key"):
                return media_gen_config["api_key"]

    # 2. From provider-specific env var (registered env_key)
    env_key = MediaGenProviderRegistry.get_env_key(provider_name)
    if env_key:
        val = os.environ.get(env_key)
        if val:
            return val

    # 3. Provider-specific fallbacks (from registry module)
    fallback_keys = PROVIDER_ENV_FALLBACKS.get(provider_name, [])
    for key in fallback_keys:
        val = os.environ.get(key)
        if val:
            return val

    # 4. Common fallbacks
    for key in ["OPENAI_API_KEY", "MEDIA_GEN_API_KEY"]:
        val = os.environ.get(key)
        if val:
            return val

    return None


class GenerateImageTool(ToolBase):
    """AI 图片生成工具

    支持多 Provider 图片生成：
    - OpenAI: dall-e-3, dall-e-2, gpt-image-1
    - 阿里云通义万相: wan2.6-t2i, wan2.5-t2i-preview, wanx2.1-t2i-turbo, wanx-v1 等
    - Google Nano Banana: gemini-2.5-flash-image-preview (支持图片编辑)
    """

    def _define_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="generate_image",
            display_name="Generate Image",
            description=_GENERATE_IMAGE_PROMPT,
            category=ToolCategory.MEDIA_GEN,
            risk_level=ToolRiskLevel.MEDIUM,
            source=ToolSource.SYSTEM,
            requires_permission=True,
            timeout=180,
            tags=["image", "generation", "ai", "media", "dall-e", "wanxiang", "wanx", "google", "banana"],
            author="openderisk",
        )

    def _define_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": (
                        "图片描述/提示词。通义万相和 Google Nano Banana 支持中英文，OpenAI 建议用英文。"
                        "详细描述画面内容、风格、构图等。"
                    ),
                },
                "provider": {
                    "type": "string",
                    "description": (
                        "生成服务提供商: 'openai' (DALL-E), 'wanxiang' (通义万相), 'google' (Nano Banana)"
                    ),
                    "default": "openai",
                },
                "model": {
                    "type": "string",
                    "description": (
                        "模型名称。OpenAI: dall-e-3, dall-e-2, gpt-image-1; "
                        "通义万相: wan2.6-t2i, wan2.5-t2i-preview, wan2.2-t2i-flash, "
                        "wan2.2-t2i-plus, wanx2.1-t2i-turbo, wanx2.1-t2i-plus, "
                        "wanx2.0-t2i-turbo, wanx-v1; "
                        "Google: gemini-2.5-flash-image-preview, gemini-2.5-flash-image"
                    ),
                    "default": "dall-e-3",
                },
                "size": {
                    "type": "string",
                    "description": (
                        "图片尺寸。OpenAI: '1024x1024', '1024x1792', '1792x1024', '512x512'; "
                        "通义万相: '1280*1280', '1024*1024', '720*1280', '768*1152', '1280*720' "
                        "(使用 * 分隔宽高); Google Nano Banana 不支持自定义尺寸"
                    ),
                    "default": "1024x1024",
                },
                "image_url": {
                    "type": "string",
                    "description": (
                        "参考图片 URL (仅 Google Nano Banana 支持，用于图片编辑模式)。"
                        "传入后模型将基于该图片进行编辑。"
                        "支持公网 URL 和 Base64 编码 (data:image/xxx;base64,...)"
                    ),
                },
                "quality": {
                    "type": "string",
                    "enum": ["standard", "hd"],
                    "description": "图片质量 (仅 OpenAI dall-e-3 支持 hd)",
                    "default": "standard",
                },
                "style": {
                    "type": "string",
                    "description": (
                        "图片风格。OpenAI dall-e-3: 'vivid', 'natural'; "
                        "通义万相 wanx-v1: 'auto', 'photography', 'portrait', '3d_cartoon', "
                        "'anime', 'oil_painting', 'watercolor', 'sketch', 'chinese_painting', "
                        "'flat_illustration'"
                    ),
                    "default": "vivid",
                },
                "negative_prompt": {
                    "type": "string",
                    "description": (
                        "反向提示词，描述不希望在画面中看到的内容 (仅通义万相支持)。"
                        "例如: '低分辨率，模糊，变形，多余的手指'"
                    ),
                },
                "n": {
                    "type": "integer",
                    "description": "生成图片数量 (1-4)，通义万相默认4张，建议设为1以节省配额",
                    "minimum": 1,
                    "maximum": 4,
                },
                "watermark": {
                    "type": "boolean",
                    "description": "是否添加AI水印 (仅通义万相 wan2.6+ 支持，默认 false)",
                    "default": False,
                },
                "seed": {
                    "type": "integer",
                    "description": "随机数种子，用于复现结果 (仅通义万相支持)",
                    "minimum": 0,
                },
                "description": {
                    "type": "string",
                    "description": "交付文件描述 (可选)",
                },
            },
            "required": ["prompt"],
        }

    def to_openai_tool(self) -> Dict[str, Any]:
        """Override to dynamically inject available providers/models into description."""
        tool_dict = super().to_openai_tool()
        try:
            from derisk.agent.util.media_gen.provider_registry import MediaGenProviderRegistry
            availability = MediaGenProviderRegistry.format_available_summary()
            if availability:
                tool_dict["function"]["description"] = (
                    tool_dict["function"]["description"] + "\n\n" + availability
                )
        except Exception as e:
            logger.debug(f"[generate_image] Failed to inject dynamic availability: {e}")
        return tool_dict

    async def execute(
        self, args: Dict[str, Any], context: Optional[ToolContext] = None
    ) -> ToolResult:
        prompt = args.get("prompt", "").strip()
        if not prompt:
            return ToolResult.fail(error="prompt 不能为空", tool_name=self.name)

        provider_name = args.get("provider", "openai")
        model = args.get("model", "dall-e-3")
        description = args.get("description", "").strip() or f"AI 生成图片: {prompt[:50]}"

        # Resolve provider
        from derisk.agent.util.media_gen.provider_registry import MediaGenProviderRegistry

        api_key = _resolve_api_key(provider_name, context)
        if not api_key:
            return ToolResult.fail(
                error=f"未找到 {provider_name} 的 API Key。请设置环境变量或在配置中提供。",
                tool_name=self.name,
            )

        provider = MediaGenProviderRegistry.create_provider(
            name=provider_name, api_key=api_key
        )
        if not provider:
            available = list(MediaGenProviderRegistry.list_providers().keys())
            return ToolResult.fail(
                error=f"未找到生成服务 '{provider_name}'。可用服务: {available}",
                tool_name=self.name,
            )

        # Generate image
        try:
            # Collect all supported generation parameters
            gen_kwargs = {}
            for k in ("size", "quality", "style", "negative_prompt", "n",
                      "watermark", "seed", "image_url", "timeout"):
                v = args.get(k)
                if v is not None and v != "":
                    gen_kwargs[k] = v

            result = await provider.generate_image(prompt, model, **gen_kwargs)
        except NotImplementedError:
            return ToolResult.fail(
                error=f"服务 '{provider_name}' 不支持图片生成",
                tool_name=self.name,
            )
        except Exception as e:
            logger.error(f"[generate_image] Generation failed: {e}", exc_info=True)
            return ToolResult.fail(
                error=f"图片生成失败: {e}",
                tool_name=self.name,
            )

        # Save and deliver
        file_name = f"generated_image_{uuid.uuid4().hex[:8]}.{result.format}"
        return await self._save_and_deliver(
            result, file_name, description, context, prompt
        )

    async def _save_and_deliver(
        self,
        result: Any,
        file_name: str,
        description: str,
        context: Optional[ToolContext],
        prompt: str,
    ) -> ToolResult:
        """Save generated media to storage and render d-attach component."""
        afs = _get_agent_file_system(context)

        preview_url = None
        dattach_md = ""

        if afs:
            try:
                from derisk.agent.core.memory.gpts.file_base import FileType

                file_key = file_name.rsplit(".", 1)[0]
                extension = file_name.rsplit(".", 1)[1] if "." in file_name else result.format

                file_metadata = await afs.save_binary_file(
                    file_key=file_key,
                    data=result.data,
                    file_type=FileType.DELIVERABLE,
                    extension=extension,
                    file_name=file_name,
                    tool_name="generate_image",
                    is_deliverable=True,
                    description=description,
                    metadata={
                        "file_category": "deliverable",
                        "mime_type": result.mime_type,
                        "prompt": prompt[:200],
                        **(result.metadata or {}),
                    },
                )

                if file_metadata:
                    preview_url = file_metadata.preview_url

                    # Render d-attach component
                    try:
                        from derisk.agent.core.file_system.dattach_utils import render_dattach

                        dattach_md = render_dattach(
                            file_name=file_name,
                            file_url=preview_url or "",
                            file_type="deliverable",
                            object_path=file_metadata.metadata.get("object_path") if file_metadata.metadata else None,
                            preview_url=preview_url,
                            download_url=file_metadata.download_url or preview_url,
                            description=description,
                            mime_type=result.mime_type,
                        )
                    except Exception as e:
                        logger.warning(f"[generate_image] d-attach render failed: {e}")

            except Exception as e:
                logger.warning(f"[generate_image] AFS save failed: {e}", exc_info=True)

        # Build output
        parts = [
            f"✅ 图片生成成功: {file_name}",
            f"📋 描述: {description}",
            f"🎨 模型: {result.metadata.get('model', 'unknown')}",
        ]

        if result.metadata.get("provider"):
            parts.append(f"🔌 服务商: {result.metadata['provider']}")

        if result.metadata.get("revised_prompt"):
            parts.append(f"📝 优化后的提示词: {result.metadata['revised_prompt']}")

        if result.metadata.get("image_url"):
            parts.append(f"🔗 原始图片链接: {result.metadata['image_url']}")

        if preview_url:
            parts.append(f"\n![{description}]({preview_url})")

        if dattach_md:
            parts.append(f"\n\n**交付文件:**\n{dattach_md}")
        elif preview_url:
            parts.append(f"\n**下载链接:** {preview_url}")

        artifact = Artifact(
            name=file_name,
            type="image",
            url=preview_url,
            mime_type=result.mime_type,
            size=len(result.data),
            metadata=result.metadata,
        )

        return ToolResult.ok(
            output="\n".join(parts),
            tool_name=self.name,
            artifacts=[artifact],
        )


class GenerateVideoTool(ToolBase):
    """AI 视频生成工具

    支持多 Provider 视频生成：
    - OpenAI: Sora
    - 火山引擎豆包 Seedance: doubao-seedance-2-0-250428, doubao-seedance-1-5-pro-251215 等
    - 支持 文生视频、图生视频 (首帧)、首尾帧生视频
    """

    def _define_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="generate_video",
            display_name="Generate Video",
            description=_GENERATE_VIDEO_PROMPT,
            category=ToolCategory.MEDIA_GEN,
            risk_level=ToolRiskLevel.MEDIUM,
            source=ToolSource.SYSTEM,
            requires_permission=True,
            timeout=600,
            tags=["video", "generation", "ai", "media", "sora", "seedance", "doubao"],
            author="openderisk",
        )

    def _define_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": (
                        "视频描述/提示词。通义万相和 Seedance 均支持中英文。"
                        "详细描述场景、动作、镜头运动、光影等。"
                    ),
                },
                "provider": {
                    "type": "string",
                    "description": (
                        "生成服务提供商: 'openai_video' (Sora) 或 'seedance' (豆包 Seedance)"
                    ),
                    "default": "openai_video",
                },
                "model": {
                    "type": "string",
                    "description": (
                        "模型名称。OpenAI: 'sora'; "
                        "Seedance: 'doubao-seedance-2-0-250428', 'doubao-seedance-1-5-pro-251215', "
                        "'doubao-seedance-1-0-pro-250428', 'doubao-seedance-1-0-pro-fast-250428'"
                    ),
                    "default": "sora",
                },
                "image_url": {
                    "type": "string",
                    "description": (
                        "首帧图片 URL (图生视频模式，仅 Seedance 支持)。"
                        "支持公网 URL 和 Base64 编码 (data:image/xxx;base64,...)。"
                        "提供此参数后，模型将以该图片作为视频第一帧生成视频。"
                    ),
                },
                "image_url_last": {
                    "type": "string",
                    "description": (
                        "尾帧图片 URL (首尾帧生视频模式，仅 Seedance 2.0/1.5 Pro/1.0 Pro 支持)。"
                        "必须与 image_url 同时使用。模型将以 image_url 为首帧、image_url_last 为尾帧生成视频。"
                    ),
                },
                "duration": {
                    "type": "integer",
                    "description": "视频时长 (秒)。Seedance 范围 1-15 秒",
                    "default": 5,
                    "minimum": 1,
                    "maximum": 60,
                },
                "resolution": {
                    "type": "string",
                    "enum": ["480p", "720p", "1080p", "4k"],
                    "description": (
                        "视频分辨率。Seedance 2.0/1.5 Pro 默认 720p; "
                        "Seedance 1.0 Pro 默认 1080p; "
                        "4k 仅 Seedance 2.0 支持"
                    ),
                    "default": "720p",
                },
                "aspect_ratio": {
                    "type": "string",
                    "enum": ["16:9", "4:3", "1:1", "3:4", "9:16", "21:9", "adaptive"],
                    "description": (
                        "视频宽高比。'adaptive' 表示根据输入自动选择 (仅 Seedance 支持)"
                    ),
                    "default": "16:9",
                },
                "seed": {
                    "type": "integer",
                    "description": "随机数种子，用于复现结果 (仅 Seedance 支持)",
                    "minimum": 0,
                },
                "watermark": {
                    "type": "boolean",
                    "description": "是否添加水印 (仅 Seedance 支持，默认 false)",
                    "default": False,
                },
                "camera_fixed": {
                    "type": "boolean",
                    "description": "是否固定相机不移动 (仅 Seedance 支持，默认 false)",
                    "default": False,
                },
                "generate_audio": {
                    "type": "boolean",
                    "description": (
                        "是否生成同步音频 (仅 Seedance 2.0/1.5 Pro 支持，默认 true)。"
                        "设为 false 生成无声视频"
                    ),
                },
                "description": {
                    "type": "string",
                    "description": "交付文件描述 (可选)",
                },
            },
            "required": ["prompt"],
        }

    def to_openai_tool(self) -> Dict[str, Any]:
        """Override to dynamically inject available providers/models into description."""
        tool_dict = super().to_openai_tool()
        try:
            from derisk.agent.util.media_gen.provider_registry import MediaGenProviderRegistry
            availability = MediaGenProviderRegistry.format_available_summary()
            if availability:
                tool_dict["function"]["description"] = (
                    tool_dict["function"]["description"] + "\n\n" + availability
                )
        except Exception as e:
            logger.debug(f"[generate_video] Failed to inject dynamic availability: {e}")
        return tool_dict

    async def execute(
        self, args: Dict[str, Any], context: Optional[ToolContext] = None
    ) -> ToolResult:
        prompt = args.get("prompt", "").strip()
        if not prompt:
            return ToolResult.fail(error="prompt 不能为空", tool_name=self.name)

        provider_name = args.get("provider", "openai_video")
        model = args.get("model", "sora")
        description = args.get("description", "").strip() or f"AI 生成视频: {prompt[:50]}"

        from derisk.agent.util.media_gen.provider_registry import MediaGenProviderRegistry

        api_key = _resolve_api_key(provider_name, context)
        if not api_key:
            return ToolResult.fail(
                error=f"未找到 {provider_name} 的 API Key。请设置环境变量或在配置中提供。",
                tool_name=self.name,
            )

        provider = MediaGenProviderRegistry.create_provider(
            name=provider_name, api_key=api_key
        )
        if not provider:
            available = list(MediaGenProviderRegistry.list_providers().keys())
            return ToolResult.fail(
                error=f"未找到生成服务 '{provider_name}'。可用服务: {available}",
                tool_name=self.name,
            )

        # Generate video
        try:
            # Collect all supported generation parameters
            gen_kwargs = {}
            for k in ("duration", "resolution", "aspect_ratio", "image_url",
                      "image_url_last", "seed", "watermark", "camera_fixed",
                      "generate_audio", "timeout"):
                v = args.get(k)
                if v is not None and v != "":
                    gen_kwargs[k] = v

            result = await provider.generate_video(prompt, model, **gen_kwargs)
        except NotImplementedError:
            return ToolResult.fail(
                error=f"服务 '{provider_name}' 不支持视频生成",
                tool_name=self.name,
            )
        except TimeoutError as e:
            return ToolResult.fail(
                error=f"视频生成超时: {e}",
                tool_name=self.name,
            )
        except Exception as e:
            logger.error(f"[generate_video] Generation failed: {e}", exc_info=True)
            return ToolResult.fail(
                error=f"视频生成失败: {e}",
                tool_name=self.name,
            )

        # Save and deliver
        file_name = f"generated_video_{uuid.uuid4().hex[:8]}.{result.format}"
        return await self._save_and_deliver(
            result, file_name, description, context, prompt
        )

    async def _save_and_deliver(
        self,
        result: Any,
        file_name: str,
        description: str,
        context: Optional[ToolContext],
        prompt: str,
    ) -> ToolResult:
        """Save generated video to storage and render d-attach component."""
        afs = _get_agent_file_system(context)

        preview_url = None
        dattach_md = ""

        if afs:
            try:
                from derisk.agent.core.memory.gpts.file_base import FileType

                file_key = file_name.rsplit(".", 1)[0]
                extension = file_name.rsplit(".", 1)[1] if "." in file_name else result.format

                file_metadata = await afs.save_binary_file(
                    file_key=file_key,
                    data=result.data,
                    file_type=FileType.DELIVERABLE,
                    extension=extension,
                    file_name=file_name,
                    tool_name="generate_video",
                    is_deliverable=True,
                    description=description,
                    metadata={
                        "file_category": "deliverable",
                        "mime_type": result.mime_type,
                        "prompt": prompt[:200],
                        **(result.metadata or {}),
                    },
                )

                if file_metadata:
                    preview_url = file_metadata.preview_url

                    try:
                        from derisk.agent.core.file_system.dattach_utils import render_dattach

                        dattach_md = render_dattach(
                            file_name=file_name,
                            file_url=preview_url or "",
                            file_type="deliverable",
                            object_path=file_metadata.metadata.get("object_path") if file_metadata.metadata else None,
                            preview_url=preview_url,
                            download_url=file_metadata.download_url or preview_url,
                            description=description,
                            mime_type=result.mime_type,
                        )
                    except Exception as e:
                        logger.warning(f"[generate_video] d-attach render failed: {e}")

            except Exception as e:
                logger.warning(f"[generate_video] AFS save failed: {e}", exc_info=True)

        # Build output
        parts = [
            f"✅ 视频生成成功: {file_name}",
            f"📋 描述: {description}",
            f"🎬 模型: {result.metadata.get('model', 'unknown')}",
        ]

        if result.metadata.get("provider"):
            parts.append(f"🔌 服务商: {result.metadata['provider']}")

        if result.duration_seconds:
            parts.append(f"⏱️ 时长: {result.duration_seconds}s")

        if result.metadata.get("resolution"):
            parts.append(f"📐 分辨率: {result.metadata['resolution']}")

        if result.metadata.get("aspect_ratio"):
            parts.append(f"📱 宽高比: {result.metadata['aspect_ratio']}")

        if result.metadata.get("image_to_video"):
            parts.append(f"🖼️ 图生视频模式")

        if result.metadata.get("video_url"):
            parts.append(f"🔗 原始视频链接: {result.metadata['video_url']}")

        if preview_url:
            parts.append(f"\n[视频: {description}]({preview_url})")

        if dattach_md:
            parts.append(f"\n\n**交付文件:**\n{dattach_md}")
        elif preview_url:
            parts.append(f"\n**下载链接:** {preview_url}")

        artifact = Artifact(
            name=file_name,
            type="file",
            url=preview_url,
            mime_type=result.mime_type,
            size=len(result.data),
            metadata=result.metadata,
        )

        return ToolResult.ok(
            output="\n".join(parts),
            tool_name=self.name,
            artifacts=[artifact],
        )
