"""Tests for the extractor protocol & built-in extractors (RFC 004 §6)."""

from __future__ import annotations

from pathlib import Path

import pytest

from derisk.knowledge.types import ExtractMode
from derisk_ext.knowledge.extractors import (
    Extractor,
    VerbatimSpec,
    get_extractor_registry,
)
from derisk_ext.knowledge.extractors import builtin as builtin_mod
from derisk_ext.knowledge.extractors.registry_init import register_builtin_extractors


@pytest.fixture(autouse=True, scope="module")
def _ensure_builtins_registered():
    """Make sure built-ins are registered once for the whole module.

    The `@extractor` decorator runs at `builtin.py` import time and is
    idempotent (re-registrations overwrite by name), so we don't need to
    clear the registry between tests.
    """
    register_builtin_extractors()
    yield


def test_registry_has_builtins():
    reg = get_extractor_registry()
    names = {e.name for e in reg.list_all()}
    assert {"text", "pdf", "docx", "pptx", "image", "audio", "video"}.issubset(names)


def test_registry_get_by_mime():
    reg = get_extractor_registry()
    assert reg.get("text/plain").name == "text"
    assert reg.get("text/markdown").name == "text"
    assert reg.get("application/json").name == "text"
    assert reg.get("application/pdf").name == "pdf"
    assert reg.get("image/png").name == "image"
    assert reg.get("audio/mpeg").name == "audio"
    assert reg.get("application/octet-stream") is None


@pytest.mark.asyncio
async def test_text_extractor_basic(tmp_path: Path):
    reg = get_extractor_registry()
    ext = reg.get("text/plain")
    assert isinstance(ext, Extractor)

    f = tmp_path / "note.txt"
    f.write_text("hello world\nsecond line", encoding="utf-8")

    specs = await ext.extract(f, "text/plain", model=None, model_caller=None)
    assert len(specs) == 1
    spec = specs[0]
    assert isinstance(spec, VerbatimSpec)
    assert spec.content == "hello world\nsecond line"
    assert spec.source_file == "note.txt"
    assert spec.extract_mode == ExtractMode.UPLOAD
    assert spec.meta.get("mime") == "text/plain"
    assert spec.meta.get("bytes") == len(f.read_bytes())
    assert spec.content_date is not None


@pytest.mark.asyncio
async def test_text_extractor_handles_non_utf8(tmp_path: Path):
    """Non-UTF-8 bytes should not raise — fallback to replace."""
    ext = get_extractor_registry().get("text/plain")
    f = tmp_path / "bad.bin"
    f.write_bytes(b"\xff\xfe\x00bad bytes here")
    specs = await ext.extract(f, "text/plain", model=None, model_caller=None)
    assert len(specs) == 1
    assert "bad bytes here" in specs[0].content


@pytest.mark.asyncio
async def test_image_extractor_invokes_model_caller(tmp_path: Path, monkeypatch):
    """ImageExtractor should hand off to the supplied model_caller, not decode bytes."""
    ext = get_extractor_registry().get("image/png")

    # Minimal fake PNG (8-byte signature + IHDR chunk). We don't need a real
    # image — ImageExtractor just reads bytes and passes the path to the caller.
    png_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
    f = tmp_path / "snap.png"
    f.write_bytes(png_bytes)

    captured: dict = {}

    async def fake_caller(model, prompt, images=None):
        captured["model"] = model
        captured["prompt"] = prompt
        captured["images"] = images or []
        return "A photo of a cat sitting on a desk."

    specs = await ext.extract(
        f, "image/png", model="gpt-4o", model_caller=fake_caller
    )
    assert len(specs) == 1
    spec = specs[0]
    assert spec.extract_mode == ExtractMode.UPLOAD
    assert "cat" in spec.content
    assert spec.source_file == "snap.png"
    assert captured["model"] == "gpt-4o"
    assert captured["images"] == [f]


@pytest.mark.asyncio
async def test_image_extractor_without_model_caller_writes_empty_caption(tmp_path: Path):
    """Without a model_caller, ImageExtractor falls back to an empty-caption verbatim."""
    ext = get_extractor_registry().get("image/png")
    f = tmp_path / "snap.png"
    f.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 16)

    specs = await ext.extract(f, "image/png", model=None, model_caller=None)
    assert len(specs) == 1
    # Caption line is empty
    assert "Caption" in specs[0].content
    assert specs[0].meta.get("caption_len") == 0


@pytest.mark.asyncio
async def test_pdf_extractor_missing_dep_raises_clear_error(tmp_path: Path, monkeypatch):
    """If pdfplumber isn't installed, the extractor should raise a clear message."""
    ext = get_extractor_registry().get("application/pdf")
    f = tmp_path / "doc.pdf"
    f.write_bytes(b"%PDF-1.4 fake pdf")

    # Force the import to fail
    import sys

    monkeypatch.setitem(sys.modules, "pdfplumber", None)

    with pytest.raises(RuntimeError, match="pdfplumber"):
        await ext.extract(f, "application/pdf", model=None, model_caller=None)


def test_register_builtin_is_idempotent():
    """Calling register_builtin_extractors twice should not duplicate entries."""
    reg = get_extractor_registry()
    count_before = len(reg.list_all())
    register_builtin_extractors()
    count_after = len(reg.list_all())
    assert count_before == count_after


# ---------------------------------------------------------------------------
# VideoExtractor: native direct + frame-pipeline fallback
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_video_extractor_native_strategy(tmp_path: Path):
    """Native video models (gemini/qwen-vl) receive the file via videos kwarg."""
    ext = get_extractor_registry().get("video/mp4")
    assert ext is not None and ext.name == "video"

    f = tmp_path / "clip.mp4"
    f.write_bytes(b"\x00" * 1024)  # small fake file, content never read by fake caller

    captured: dict = {}

    async def fake_caller(model, prompt, images=None, videos=None):
        captured["videos"] = videos or []
        captured["images"] = images or []
        return "一段产品介绍视频,演示了上传流程。"

    specs = await ext.extract(f, "video/mp4", model="gemini-2.5-pro", model_caller=fake_caller)
    assert len(specs) == 1
    assert specs[0].meta["strategy"] == "native"
    assert "上传流程" in specs[0].content
    assert captured["videos"] == [f]
    assert captured["images"] == []


@pytest.mark.asyncio
async def test_video_extractor_falls_back_to_frames(tmp_path: Path, monkeypatch):
    """Non-native model (or native failure) → ffmpeg frame pipeline via image channel."""
    from derisk_ext.knowledge.extractors.builtin import VideoExtractor

    ext = get_extractor_registry().get("video/mp4")
    f = tmp_path / "clip.mp4"
    f.write_bytes(b"\x00" * 1024)

    # 假帧文件:管线只把路径交给 model_caller,不读内容
    frames = []
    for i in range(3):
        fp = tmp_path / f"frame_{i:03d}.jpg"
        fp.write_bytes(b"\xff\xd8\xff" + b"\x00" * 16)
        frames.append(fp)

    async def fake_frames(self, path, out_dir):
        return frames

    async def fake_audio(self, path, out_dir):
        return None

    monkeypatch.setattr(VideoExtractor, "_extract_frames", fake_frames)
    monkeypatch.setattr(VideoExtractor, "_extract_audio", fake_audio)
    monkeypatch.setattr(builtin_mod.shutil, "which", lambda name: "/usr/bin/ffmpeg")

    captured: dict = {}

    async def fake_caller(model, prompt, images=None, videos=None):
        captured["images"] = images or []
        captured["videos"] = videos or []
        return "帧序列描述了会议投屏内容。"

    # gpt-4o 不命中原生模式 → 直接走抽帧
    specs = await ext.extract(f, "video/mp4", model="gpt-4o", model_caller=fake_caller)
    assert len(specs) == 1
    assert specs[0].meta["strategy"] == "frames"
    assert specs[0].meta["frames"] == 3
    assert captured["images"] == frames
    assert captured["videos"] == []


@pytest.mark.asyncio
async def test_video_extractor_native_failure_falls_back(tmp_path: Path, monkeypatch):
    """Native-capable model that errors must degrade to the frame pipeline."""
    from derisk_ext.knowledge.extractors.builtin import VideoExtractor

    ext = get_extractor_registry().get("video/mp4")
    f = tmp_path / "clip.mp4"
    f.write_bytes(b"\x00" * 1024)

    frame = tmp_path / "frame_001.jpg"
    frame.write_bytes(b"\xff\xd8\xff" + b"\x00" * 16)

    async def fake_frames(self, path, out_dir):
        return [frame]

    async def fake_audio(self, path, out_dir):
        return None

    monkeypatch.setattr(VideoExtractor, "_extract_frames", fake_frames)
    monkeypatch.setattr(VideoExtractor, "_extract_audio", fake_audio)
    monkeypatch.setattr(builtin_mod.shutil, "which", lambda name: "/usr/bin/ffmpeg")

    calls: list = []

    async def flaky_caller(model, prompt, images=None, videos=None):
        calls.append({"images": images or [], "videos": videos or []})
        if videos:
            raise RuntimeError("provider rejected video_url")
        return "抽帧后的画面描述。"

    specs = await ext.extract(f, "video/mp4", model="qwen2.5-vl-72b", model_caller=flaky_caller)
    assert len(specs) == 1
    assert specs[0].meta["strategy"] == "frames"
    # 先尝试 native(videos),失败后走 images
    assert calls[0]["videos"] == [f]
    assert calls[1]["images"] == [frame]


@pytest.mark.asyncio
async def test_video_extractor_requires_model(tmp_path: Path):
    """No model/model_caller → clear error (unlike image, video has no text fallback)."""
    ext = get_extractor_registry().get("video/mp4")
    f = tmp_path / "clip.mp4"
    f.write_bytes(b"\x00" * 64)

    with pytest.raises(RuntimeError, match="multimodal model"):
        await ext.extract(f, "video/mp4", model=None, model_caller=None)
