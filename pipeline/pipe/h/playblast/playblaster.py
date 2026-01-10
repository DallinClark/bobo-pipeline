from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, cast

import hou

from pipe.util import Playblaster

if TYPE_CHECKING:
    from pipe.struct.db import Shot

log = logging.getLogger(__name__)


class HPlayblaster(Playblaster):
    _out_paths: dict[Playblaster.PRESET, list[Path | str]]
    _tails: tuple[int, int]

    def __init__(self) -> None:
        super().__init__()
        self._out_paths = {}
        self._tails = (0, 0)
        try:
            self.FR = int(round(hou.fps()))
        except Exception:
            pass

    def configure(
        self,
        shot: Shot,
        out_paths: dict[Playblaster.PRESET, list[Path | str]],
        tails: tuple[int, int] = (0, 0),
    ) -> "HPlayblaster":
        self._shot = shot
        self._out_paths = out_paths
        self._tails = tails
        return self

    def _run_postprocess(self, video_path: Path) -> None:
        # Keep the H.265 output as-is for now.
        return

    def _write_images(self, path: str) -> None:
        start_frame = int(self._shot.cut_in) - self._tails[0]
        end_frame = int(self._shot.cut_out) + self._tails[1]

        scene_viewer, viewport = _get_scene_viewer_and_viewport()
        settings = _get_flipbook_settings(scene_viewer, viewport)

        _configure_flipbook(settings, path, start_frame, end_frame)
        _set_viewport_renderer_vk(viewport)
        _run_flipbook(scene_viewer, viewport, settings)

    def playblast(self) -> None:
        with self(self._shot):
            super()._do_playblast(self._out_paths, self._tails)


def _get_scene_viewer_and_viewport() -> tuple[hou.SceneViewer, hou.GeometryViewport]:
    scene_viewer_tab = hou.ui.paneTabOfType(hou.paneTabType.SceneViewer)
    if scene_viewer_tab is None:
        raise RuntimeError("No Scene Viewer found for flipbook export.")

    scene_viewer = cast(hou.SceneViewer, scene_viewer_tab)
    viewport = scene_viewer.curViewport()
    if viewport is None:
        raise RuntimeError("No active viewport found for flipbook export.")

    return scene_viewer, viewport


def _get_flipbook_settings(
    scene_viewer: hou.SceneViewer, viewport: hou.GeometryViewport
) -> hou.FlipbookSettings:
    settings = None
    if hasattr(scene_viewer, "flipbookSettings"):
        settings = scene_viewer.flipbookSettings()
    elif hasattr(viewport, "flipbookSettings"):
        settings = viewport.flipbookSettings()

    if settings is None:
        raise RuntimeError("Unable to access flipbook settings.")

    if hasattr(settings, "stash"):
        settings = settings.stash()

    return settings


def _configure_flipbook(
    settings: hou.FlipbookSettings,
    path: str,
    start_frame: int,
    end_frame: int,
) -> None:
    output_path = f"{path}.$F4.png"
    if not _try_set_output_path(settings, output_path):
        raise RuntimeError("Unable to set flipbook output path.")

    if not _try_set_frame_range(settings, start_frame, end_frame):
        raise RuntimeError("Unable to set flipbook frame range.")

    _try_set_flag(settings, True, ("useFrameRange", "setUseFrameRange"))
    _try_set_flag(
        settings,
        True,
        ("useOutputFile", "setUseOutputFile", "setOutputToFile"),
    )
    _try_set_flag(
        settings,
        False,
        ("useMPlay", "setUseMPlay", "setOutputToMPlay"),
    )


def _try_set_output_path(settings: hou.FlipbookSettings, output_path: str) -> bool:
    for method_name in ("output", "setOutput", "setOutputPath", "setOutputFile"):
        if hasattr(settings, method_name):
            try:
                getattr(settings, method_name)(output_path)
                return True
            except TypeError:
                continue
    return False


def _try_set_frame_range(
    settings: hou.FlipbookSettings, start_frame: int, end_frame: int
) -> bool:
    if hasattr(settings, "frameRange"):
        try:
            settings.frameRange((start_frame, end_frame))
            return True
        except TypeError:
            pass

    if hasattr(settings, "setFrameRange"):
        try:
            settings.setFrameRange(start_frame, end_frame)
            return True
        except TypeError:
            try:
                settings.setFrameRange((start_frame, end_frame))
                return True
            except TypeError:
                pass

    return False


def _try_set_flag(
    settings: hou.FlipbookSettings, value: bool, method_names: tuple[str, ...]
) -> bool:
    for method_name in method_names:
        if hasattr(settings, method_name):
            try:
                getattr(settings, method_name)(value)
                return True
            except TypeError:
                continue
    return False


def _set_viewport_renderer_vk(viewport: hou.GeometryViewport) -> None:
    try:
        settings = viewport.settings()
    except Exception:
        log.warning("Could not access viewport settings to set renderer.")
        return

    renderer_candidates: list[object] = []
    for enum_name in ("viewportRenderer", "geometryViewportRenderer"):
        enum = getattr(hou, enum_name, None)
        if not enum:
            continue
        for member in ("VK", "Vulkan"):
            if hasattr(enum, member):
                renderer_candidates.append(getattr(enum, member))

    renderer_candidates.extend(
        ["Houdini VK", "VK", "Vulkan", "HD_HoudiniRendererPlugin"]
    )

    for candidate in renderer_candidates:
        if _apply_renderer(settings, viewport, candidate):
            return

    log.warning("Could not set viewport renderer to VK; using current renderer.")


def _apply_renderer(
    settings: hou.GeometryViewportSettings,
    viewport: hou.GeometryViewport,
    renderer: object,
) -> bool:
    for target in (settings, viewport):
        for method_name in ("setRenderer", "setRendererPlugin"):
            if hasattr(target, method_name):
                try:
                    getattr(target, method_name)(renderer)
                    if target is settings and hasattr(viewport, "setSettings"):
                        viewport.setSettings(settings)
                    return True
                except Exception:
                    continue
    return False


def _run_flipbook(
    scene_viewer: hou.SceneViewer,
    viewport: hou.GeometryViewport,
    settings: hou.FlipbookSettings,
) -> None:
    flipbook = getattr(viewport, "flipbook", None)
    if callable(flipbook):
        try:
            flipbook(settings)
            return
        except Exception:
            pass

    try:
        scene_viewer.flipbook(viewport, settings)
    except Exception as exc:
        log.error("Flipbook failed: %s", exc, exc_info=True)
        raise
