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
| wanxiang | qwen-image-3.0-pro, wan2.6-t2i, wan2.5-t2i-preview, wan2.2-t2i-flash, wan2.2-t2i-plus, wanx2.1-t2i-turbo, wanx2.1-t2i-plus, wanx2.0-t2i-turbo, wanx-v1 | 阿里云通义万相 / 千问图像 |
| google | gemini-2.5-flash-image-preview, gemini-2.5-flash-image | Google Nano Banana (支持图片生成和编辑) |

**使用场景：**
- 根据文字描述生成图片
- 生成数据可视化、插图、概念图等
- Google Nano Banana 还支持图片编辑 (通过 image_url 传入参考图)
- qwen-image-3.0-pro 支持图生图/图像编辑 (I2I)：传入 1~3 张参考图 + 编辑指令，可保留人物特征换装/换场景
- 生成的图片会自动保存并交付给用户

**推荐用法：**
```
# 使用 OpenAI DALL-E 3 生成图片
generate_image(prompt="一只在星空下弹吉他的猫，赛博朋克风格", model="dall-e-3", size="1024x1024")

# 使用阿里云通义万相生成图片 (支持中英文)
generate_image(prompt="一只坐着的橘黄色的猫，表情愉悦，活泼可爱", model="wan2.6-t2i", size="1280*1280")

# 使用通义万相极速版 (更快的生成速度)
generate_image(prompt="产品界面设计图", model="wanx2.1-t2i-turbo", size="1024*1024")

# 使用千问图像 qwen-image-3.0-pro 文生图 (T2I)
generate_image(prompt="一只在星空下弹吉他的猫，赛博朋克风格", model="qwen-image-3.0-pro", size="1024*1024")

# 使用 qwen-image-3.0-pro 图生图/图像编辑 (I2I，1~3 张参考图 + 编辑指令)
generate_image(prompt="保留人物面部特征，换上都市职场穿搭，场景改为高端咖啡店", model="qwen-image-3.0-pro", reference_images=["https://example.com/portrait.jpg"], size="1024*1024")

# 使用 Google Nano Banana 生成图片 (支持中英文)
generate_image(prompt="一只在星空下弹吉他的猫，赛博朋克风格", model="gemini-2.5-flash-image-preview")

# 使用 Google Nano Banana 编辑图片 (传入参考图)
generate_image(prompt="把背景改成日落场景", model="gemini-2.5-flash-image-preview", image_url="https://example.com/original.jpg")

# 使用反向提示词 (排除不想要的内容)
generate_image(prompt="一座美丽的城市夜景", model="wan2.6-t2i", negative_prompt="低分辨率，模糊，变形")
```

**注意事项：**
- 生成图片需要消耗 API 配额，请合理使用
- 图片生成通常需要 10-60 秒 (通义万相异步任务可能需要更长时间)
- 生成的图片会自动上传到存储并生成交付链接
- OpenAI 需设置 OPENAI_API_KEY 环境变量
- 通义万相 / 千问图像需设置 DASHSCOPE_API_KEY 环境变量
- Google Nano Banana 需设置 GOOGLE_API_KEY 环境变量
- qwen-image-3.0-pro 目前处于邀测阶段，需在阿里云百炼模型广场申请开通后方可使用
"""

_GENERATE_VIDEO_PROMPT = """使用 AI 模型生成视频。

**支持的 Provider 和模型：**

| Provider | 模型 | 说明 |
|----------|------|------|
| openai_video | sora | OpenAI Sora |
| seedance | doubao-seedance-2-0-250428, doubao-seedance-1-5-pro-251215, doubao-seedance-1-0-pro-250428, doubao-seedance-1-0-pro-fast-250428 | 火山引擎豆包 Seedance |
| happyhorse | happyhorse-1.1-t2v, happyhorse-1.0-t2v, happyhorse-1.1-i2v, happyhorse-1.0-i2v, happyhorse-1.1-r2v, happyhorse-1.0-r2v | 阿里云 HappyHorse (文生/图生/参考生视频) |

**使用场景：**
- 根据文字描述生成短视频 (文生视频)
- 根据首帧图片 + 文字描述生成视频 (图生视频)
- 根据首帧 + 尾帧图片生成视频 (首尾帧生视频，仅 Seedance)
- 根据多张参考图 + 文字描述生成视频 (参考生视频，仅 HappyHorse r2v，1~9 张参考图)
- 生成产品演示、概念视频等

**HappyHorse 模型选择（按场景）：**
- 文生视频：`happyhorse-1.1-t2v` (无需图片)
- 图生视频：`happyhorse-1.1-i2v` (需传 `image_url` 作首帧)
- 参考生视频：`happyhorse-1.1-r2v` (需传 `reference_images`，1~9 张；prompt 中用 `[Image 1]`/`[Image 2]` 指代参考图)

**推荐用法：**
```
# 使用 OpenAI Sora 生成视频
generate_video(prompt="日落时分海浪拍打沙滩的慢镜头", model="sora", duration=5)

# 使用火山引擎 Seedance 文生视频
generate_video(prompt="一只小猫对着镜头打哈欠", model="doubao-seedance-1-0-pro-250428", duration=5, resolution="720p")

# 使用 Seedance 图生视频 (首帧图片)
generate_video(prompt="镜头缓慢推进，女孩转头微笑", model="doubao-seedance-2-0-250428", image_url="https://example.com/first_frame.jpg", duration=5)

# 使用 Seedance 首尾帧生视频
generate_video(prompt="从白天过渡到夜晚", model="doubao-seedance-1-5-pro-251215", image_url="https://example.com/day.jpg", image_url_last="https://example.com/night.jpg", duration=5)

# 使用阿里云 HappyHorse 文生视频
generate_video(prompt="一只在草地上奔跑的猫", model="happyhorse-1.1-t2v", duration=5, resolution="720p")

# 使用 HappyHorse 图生视频 (首帧图片)
generate_video(prompt="镜头缓慢推进，城市夜景灯火亮起", model="happyhorse-1.1-i2v", image_url="https://example.com/first_frame.jpg", duration=5)

# 使用 HappyHorse 参考生视频 (多张参考图，prompt 中用 [Image 1]/[Image 2] 指代)
generate_video(prompt="[Image 1]中身着红色旗袍的女性，手持[Image 2]中的折扇，镜头缓缓推近", model="happyhorse-1.1-r2v", reference_images=["https://example.com/girl.jpg", "https://example.com/fan.jpg"], duration=5)

# 生成无声视频
generate_video(prompt="城市夜景延时摄影", model="doubao-seedance-2-0-250428", generate_audio=false)
```

**注意事项：**
- 视频生成需要较长时间 (通常 1-10 分钟)
- 视频生成消耗较多 API 配额
- 生成的视频会自动上传到存储并生成交付链接
- OpenAI 需设置 OPENAI_API_KEY 环境变量
- 火山引擎需设置 ARK_API_KEY 环境变量
- 阿里云 HappyHorse 需设置 DASHSCOPE_API_KEY 环境变量
- image_url / reference_images 支持公网 URL 和 Base64 编码 (data:image/xxx;base64,...)
- HappyHorse i2v 的宽高比跟随首帧图，不支持 aspect_ratio；t2v/r2v 支持 aspect_ratio
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


def _resolve_media_model(
    model: str,
) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Resolve (protocol, api_key, base_url) for a media-gen model by name.

    Looks up ``ModelConfigCache`` by model name. The protocol (selected in the
    model-config UI) determines the provider class / API shape. ``api_key``
    falls back to the env var for that protocol if the config has none.
    ``base_url`` comes from the config (else the provider uses its default).

    Returns ``(None, None, None)`` if the model is not configured as a
    media-gen model (protocol not in MEDIA_PROTOCOLS).
    """
    from derisk.agent.util.llm.model_config_cache import (
        ModelConfigCache,
        MEDIA_PROTOCOLS,
    )
    from derisk.agent.util.media_gen.provider_registry import (
        MediaGenProviderRegistry,
    )

    try:
        cfg = ModelConfigCache.get_config(model)
    except Exception as e:
        logger.debug(f"[media_gen] ModelConfigCache lookup failed for '{model}': {e}")
        return None, None, None

    if not cfg or cfg.get("protocol") not in MEDIA_PROTOCOLS:
        return None, None, None

    protocol = cfg["protocol"]
    api_key = cfg.get("api_key") or MediaGenProviderRegistry.get_env_api_key(protocol)
    base_url = cfg.get("base_url") or cfg.get("api_base")
    return protocol, api_key, base_url


class GenerateImageTool(ToolBase):
    """AI 图片生成工具

    支持多 Provider 图片生成：
    - OpenAI: dall-e-3, dall-e-2, gpt-image-1
    - 阿里云通义万相/千问图像: wan2.6-t2i, wan2.5-t2i-preview, wanx2.1-t2i-turbo, wanx-v1 等; qwen-image-3.0-pro (T2I + I2I 图像编辑)
    - Google Nano Banana: gemini-2.5-flash-image-preview (支持图片生成和编辑)
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
                "model": {
                    "type": "string",
                    "description": (
                        "模型名称（从下方「当前可用的媒体生成模型」列表中选择；"
                        "该模型需先在系统配置-模型配置里以媒体生成协议配置）。"
                        "如 qwen-image-3.0-pro、wan2.6-t2i、dall-e-3、gemini-2.5-flash-image-preview 等。"
                        "模型名随便填，系统按模型名查协议自动路由。"
                    ),
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
                        "参考图片 URL，用于图片编辑/图生图模式。"
                        "Google Nano Banana 和 qwen-image-3.0-pro 支持。"
                        "传入后模型将基于该图片进行编辑。"
                        "支持公网 URL 和 Base64 编码 (data:image/xxx;base64,...)。"
                        "qwen-image-3.0-pro 若需多张参考图请改用 reference_images。"
                    ),
                },
                "reference_images": {
                    "type": "array",
                    "description": (
                        "参考图片 URL 列表 (图生图/图像编辑 I2I，仅 qwen-image-3.0-pro 支持，1~3 张)。"
                        "传入后模型将基于这些图片结合 prompt 进行编辑/生成。"
                        "支持公网 URL 和 Base64 编码 (data:image/xxx;base64,...)。"
                    ),
                    "items": {
                        "type": "string",
                        "description": "参考图片 URL",
                    },
                },
                "prompt_extend": {
                    "type": "boolean",
                    "description": (
                        "是否开启提示词智能改写 (仅 qwen-image-3.0-pro 支持，默认 true)。"
                        "开启后模型会优化正向提示词，对简单描述提升明显"
                    ),
                    "default": True,
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
        """动态注入可用模型列表与默认模型到工具描述/schema。"""
        tool_dict = super().to_openai_tool()
        try:
            from derisk.agent.util.media_gen.provider_registry import MediaGenProviderRegistry

            # 把系统配置的默认模型写进 schema default，LLM 不传 model 时即用此值
            default_model = MediaGenProviderRegistry.get_default_image_model()
            if default_model:
                props = tool_dict.get("function", {}).get("parameters", {}).get("properties", {})
                if "model" in props:
                    props["model"]["default"] = default_model

            availability = MediaGenProviderRegistry.format_available_summary(capability="image")
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

        from derisk.agent.util.media_gen.provider_registry import MediaGenProviderRegistry

        # 模型优先级：工具显式传参 > 系统配置默认 > 第一个可用模型
        model = (
            args.get("model")
            or MediaGenProviderRegistry.get_default_image_model()
            or MediaGenProviderRegistry.get_first_usable_model("image")
        )
        if not model:
            return ToolResult.fail(
                error="未配置任何可用的图片生成模型。请在「系统配置 → 媒体生成」设置默认模型，"
                      "或在模型管理中配置图片生成模型（protocol 为 dashscope_image/openai_image/google_image）。",
                tool_name=self.name,
            )

        protocol, api_key, base_url = _resolve_media_model(model)
        if not protocol:
            return ToolResult.fail(
                error=f"未找到模型 '{model}' 对应的图片生成服务。"
                      f"请确认该模型已在模型管理中配置且 protocol 属于图片生成协议。",
                tool_name=self.name,
            )
        if not api_key:
            return ToolResult.fail(
                error=f"未找到模型 '{model}' (protocol={protocol}) 的 API Key。"
                      f"请在模型配置中填写 api_key，或设置对应的环境变量。",
                tool_name=self.name,
            )

        provider = MediaGenProviderRegistry.create_provider_by_protocol(
            protocol=protocol, api_key=api_key, base_url=base_url
        )
        if not provider:
            return ToolResult.fail(
                error=f"protocol '{protocol}' 未注册对应的图片生成 provider。",
                tool_name=self.name,
            )

        # Generate image
        try:
            # Collect all supported generation parameters
            gen_kwargs = {}
            for k in ("size", "quality", "style", "negative_prompt", "n",
                      "watermark", "seed", "image_url", "prompt_extend", "timeout"):
                v = args.get(k)
                if v is not None and v != "":
                    gen_kwargs[k] = v

            # reference_images (list) - only pass when non-empty (qwen-image-3.0 I2I)
            reference_images = args.get("reference_images")
            if reference_images:
                gen_kwargs["reference_images"] = reference_images

            result = await provider.generate_image(prompt, model, **gen_kwargs)
        except NotImplementedError:
            return ToolResult.fail(
                error=f"模型 '{model}' (protocol={protocol}) 不支持图片生成",
                tool_name=self.name,
            )
        except Exception as e:
            logger.error(f"[generate_image] Generation failed: {e}", exc_info=True)
            return ToolResult.fail(
                error=f"图片生成失败: {e}",
                tool_name=self.name,
            )

        # Save and deliver
        description = args.get("description", "").strip() or f"AI 生成图片: {prompt[:50]}"
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
    - 阿里云 HappyHorse: happyhorse-1.1-t2v/-i2v/-r2v (及 1.0 版本)
    - 支持 文生视频、图生视频 (首帧)、首尾帧生视频、参考生视频 (多参考图，仅 HappyHorse r2v)
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
                "model": {
                    "type": "string",
                    "description": (
                        "模型名称（从下方「当前可用的媒体生成模型」列表中选择；"
                        "该模型需先在系统配置-模型配置里以媒体生成协议配置）。"
                        "如 happyhorse-1.1-t2v (文生视频)、happyhorse-1.1-i2v (图生视频，需 image_url)、"
                        "happyhorse-1.1-r2v (参考生视频，需 reference_images)、sora、doubao-seedance-2-0-250428 等。"
                        "模型名随便填，系统按模型名查协议自动路由。"
                    ),
                },
                "image_url": {
                    "type": "string",
                    "description": (
                        "首帧图片 URL (图生视频模式)。Seedance 和 HappyHorse i2v 均支持。"
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
                "reference_images": {
                    "type": "array",
                    "description": (
                        "参考图片 URL 列表 (参考生视频 r2v 模式，仅 HappyHorse happyhorse-*-r2v 支持，1~9 张)。"
                        "prompt 中用 [Image 1]/[Image 2]/[Image 3] 指代列表中的参考图。"
                        "支持公网 URL 和 Base64 编码 (data:image/xxx;base64,...)。"
                    ),
                    "items": {
                        "type": "string",
                        "description": "参考图片 URL",
                    },
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
                    "enum": ["16:9", "4:3", "1:1", "3:4", "9:16", "21:9", "4:5", "5:4", "9:21", "adaptive"],
                    "description": (
                        "视频宽高比。Seedance/t2v/r2v 支持 16:9/4:3/1:1/3:4/9:16/21:9/4:5/5:4/9:21。"
                        "'adaptive' 表示根据输入自动选择 (仅 Seedance 支持)。"
                        "HappyHorse i2v 跟随首帧图宽高比，忽略此参数"
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
        """动态注入可用模型列表与默认模型到工具描述/schema。"""
        tool_dict = super().to_openai_tool()
        try:
            from derisk.agent.util.media_gen.provider_registry import MediaGenProviderRegistry

            # 把系统配置的默认模型写进 schema default，LLM 不传 model 时即用此值
            default_model = MediaGenProviderRegistry.get_default_video_model()
            if default_model:
                props = tool_dict.get("function", {}).get("parameters", {}).get("properties", {})
                if "model" in props:
                    props["model"]["default"] = default_model

            availability = MediaGenProviderRegistry.format_available_summary(capability="video")
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

        from derisk.agent.util.media_gen.provider_registry import MediaGenProviderRegistry

        # 模型优先级：工具显式传参 > 系统配置默认 > 第一个可用模型
        model = (
            args.get("model")
            or MediaGenProviderRegistry.get_default_video_model()
            or MediaGenProviderRegistry.get_first_usable_model("video")
        )
        if not model:
            return ToolResult.fail(
                error="未配置任何可用的视频生成模型。请在「系统配置 → 媒体生成」设置默认模型，"
                      "或在模型管理中配置视频生成模型（protocol 为 dashscope_video/volcengine_video/openai_video）。",
                tool_name=self.name,
            )

        protocol, api_key, base_url = _resolve_media_model(model)
        if not protocol:
            return ToolResult.fail(
                error=f"未找到模型 '{model}' 对应的视频生成服务。"
                      f"请确认该模型已在模型管理中配置且 protocol 属于视频生成协议。",
                tool_name=self.name,
            )
        if not api_key:
            return ToolResult.fail(
                error=f"未找到模型 '{model}' (protocol={protocol}) 的 API Key。"
                      f"请在模型配置中填写 api_key，或设置对应的环境变量。",
                tool_name=self.name,
            )

        provider = MediaGenProviderRegistry.create_provider_by_protocol(
            protocol=protocol, api_key=api_key, base_url=base_url
        )
        if not provider:
            return ToolResult.fail(
                error=f"protocol '{protocol}' 未注册对应的视频生成 provider。",
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

            # reference_images (list) — only pass when non-empty (HappyHorse r2v)
            reference_images = args.get("reference_images")
            if reference_images:
                gen_kwargs["reference_images"] = reference_images

            result = await provider.generate_video(prompt, model, **gen_kwargs)
        except NotImplementedError:
            return ToolResult.fail(
                error=f"模型 '{model}' (protocol={protocol}) 不支持视频生成",
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
        description = args.get("description", "").strip() or f"AI 生成视频: {prompt[:50]}"
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


# 模型能力描述（按模型名后缀推断输入模式）
def _infer_model_capabilities(model: str, protocol: str) -> List[str]:
    """根据模型名后缀推断支持的输入模式（文生/图生/参考生等）。"""
    m = (model or "").lower()
    caps: List[str] = []

    # 视频模型
    if "-t2v" in m or m.endswith("t2v") or m == "sora":
        caps.append("text-to-video (文生视频)")
    if "-i2v" in m or m.endswith("i2v"):
        caps.append("image-to-video (图生视频，首帧)")
    if "-r2v" in m or m.endswith("r2v"):
        caps.append("reference-to-video (参考生视频，多图)")

    # 图片模型
    if "qwen-image" in m or "-t2i" in m or m.startswith("wan") or m.startswith("wanx") or "dall-e" in m:
        caps.append("text-to-image (文生图)")
    if "qwen-image" in m:
        caps.append("image-to-image (图生图/图像编辑，参考图 1~3 张)")
    if "gemini" in m and "image" in m:
        caps.append("image-editing (图片编辑，参考图)")

    # 兜底：如果没匹配到，按 protocol 给基础能力
    if not caps:
        if "video" in protocol:
            caps.append("video generation")
        elif "image" in protocol:
            caps.append("image generation")

    return caps


def _infer_output_format(protocol: str) -> str:
    """按 protocol 推断输出格式。"""
    if "video" in protocol:
        return "video/mp4"
    if "image" in protocol:
        return "image/png"
    return "unknown"


_LIST_MEDIA_MODELS_PROMPT = """列出当前系统已配置且可用的媒体生成模型。

**用途：**
- 查看当前有哪些视频/图片生成模型可用
- 查看每个模型的类型（视频/图片）、输入模式（文生/图生/参考生）、输出格式
- 查看哪个模型是默认模型（未显式指定模型时 generate_image / generate_video 工具会使用它）
- 生成前先确认可用的模型名，避免传入不存在的模型名导致失败

**返回示例：**
```
默认视频模型: happyhorse-1.1-t2v
默认图片模型: wan2.6-t2i

视频生成模型 (2):
  - happyhorse-1.1-t2v [百炼视频]
    输入: text-to-video (文生视频)
    输出: video/mp4
    模型名: happyhorse-1.1-t2v  (默认)
  - doubao-seedance-1-0-pro-250428 [火山视频]
    输入: text-to-video (文生视频), image-to-video (图生视频，首帧)
    输出: video/mp4

图片生成模型 (1):
  - wan2.6-t2i [百炼图像]
    输入: text-to-image (文生图)
    输出: image/png
    模型名: wan2.6-t2i  (默认)
```

**注意：**
- 该工具只返回已配置且凭证有效的模型；未配置 API Key 的模型不会出现
- 若需临时使用某个模型，在 generate_image / generate_video 调用时传入对应的 model 名即可
- 默认模型可在「系统配置 → 媒体生成」中修改
"""


class ListMediaModelsTool(ToolBase):
    """列出当前可用的媒体生成模型（视频/图片）。

    非默认注入工具：仅在被请求时调用，用于让 Agent/用户实时查看
    当前已配置的媒体生成模型、类型、输入/输出与默认模型。
    """

    def _define_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="list_media_models",
            display_name="List Media Models",
            description=_LIST_MEDIA_MODELS_PROMPT,
            category=ToolCategory.MEDIA_GEN,
            risk_level=ToolRiskLevel.LOW,
            source=ToolSource.SYSTEM,
            requires_permission=False,
            timeout=10,
            tags=["media", "models", "list", "query"],
            author="openderisk",
        )

    def _define_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "capability": {
                    "type": "string",
                    "enum": ["all", "video", "image"],
                    "description": (
                        "筛选返回的模型类型: 'video' 仅视频模型, "
                        "'image' 仅图片模型, 'all' 全部 (默认 all)"
                    ),
                    "default": "all",
                },
            },
            "required": [],
        }

    async def execute(
        self, args: Dict[str, Any], context: Optional[ToolContext] = None
    ) -> ToolResult:
        capability = (args.get("capability") or "all").lower()

        from derisk.agent.util.llm.model_config_cache import (
            ModelConfigCache,
            IMAGE_PROTOCOLS,
            VIDEO_PROTOCOLS,
        )
        from derisk.agent.util.media_gen.provider_registry import (
            MediaGenProviderRegistry,
            PROTOCOL_LABELS,
        )

        default_video = MediaGenProviderRegistry.get_default_video_model()
        default_image = MediaGenProviderRegistry.get_default_image_model()

        media = ModelConfigCache.get_media_models()
        video_list, image_list = [], []
        for m in media:
            if not MediaGenProviderRegistry._is_model_usable(m):
                continue
            protocol = m.get("protocol", "")
            entry = {
                "model": m["model"],
                "protocol": protocol,
                "label": PROTOCOL_LABELS.get(protocol, protocol),
                "inputs": _infer_model_capabilities(m["model"], protocol),
                "output": _infer_output_format(protocol),
            }
            if protocol in VIDEO_PROTOCOLS:
                entry["is_default"] = (m["model"] == default_video)
                video_list.append(entry)
            elif protocol in IMAGE_PROTOCOLS:
                entry["is_default"] = (m["model"] == default_image)
                image_list.append(entry)

        video_list.sort(key=lambda x: x["model"])
        image_list.sort(key=lambda x: x["model"])

        # 构建文本输出
        parts = []
        if capability in ("all", "video"):
            parts.append(f"默认视频模型: {default_video or '（未设置，将使用第一个可用模型）'}")
            parts.append(f"\n视频生成模型 ({len(video_list)}):")
            if not video_list:
                parts.append("  （暂无可用视频模型）")
            for e in video_list:
                tag = "  (默认)" if e["is_default"] else ""
                parts.append(f"  - {e['model']} [{e['label']}]{tag}")
                parts.append(f"    输入: {', '.join(e['inputs'])}")
                parts.append(f"    输出: {e['output']}")
                parts.append(f"    模型名: {e['model']}")

        if capability == "all":
            parts.append("")

        if capability in ("all", "image"):
            parts.append(f"默认图片模型: {default_image or '（未设置，将使用第一个可用模型）'}")
            parts.append(f"\n图片生成模型 ({len(image_list)}):")
            if not image_list:
                parts.append("  （暂无可用图片模型）")
            for e in image_list:
                tag = "  (默认)" if e["is_default"] else ""
                parts.append(f"  - {e['model']} [{e['label']}]{tag}")
                parts.append(f"    输入: {', '.join(e['inputs'])}")
                parts.append(f"    输出: {e['output']}")
                parts.append(f"    模型名: {e['model']}")

        if not video_list and not image_list:
            parts = [
                "⚠️ 当前没有可用的媒体生成模型。",
                "请在「系统配置 → LLM 配置」中添加媒体生成模型（protocol 属于 "
                "dashscope_video / volcengine_video / openai_video / "
                "dashscope_image / openai_image / google_image），并配置对应的 API Key。",
            ]

        # 结构化数据放进 metadata，供程序化消费
        structured = {
            "video": video_list,
            "image": image_list,
            "defaults": {"video": default_video, "image": default_image},
        }

        return ToolResult.ok(
            output="\n".join(parts),
            tool_name=self.name,
            artifacts=[],
            metadata={"models": structured},
        )
