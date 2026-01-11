from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, cast

import hou

from pipe.util import Playblaster

from .constants import DEFAULT_RESOLUTION

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
        overrides = _apply_viewport_overrides(viewport)
        try:
            _run_flipbook(scene_viewer, viewport, settings)
        finally:
            _restore_viewport_overrides(viewport, overrides)

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
    return scene_viewer.flipbookSettings().stash()


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
    _apply_flipbook_resolution(settings, DEFAULT_RESOLUTION[0], DEFAULT_RESOLUTION[1])
    _apply_flipbook_visibility(settings)
    _try_set_flag(
        settings,
        False,
        (
            "showViewportHUD",
            "setShowViewportHUD",
            "showHUD",
            "setShowHUD",
            "showOverlay",
            "setShowOverlay",
            "displayOverlay",
            "setDisplayOverlay",
            "showText",
            "setShowText",
            "useViewportSettings",
            "setUseViewportSettings",
        ),
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


def _apply_flipbook_resolution(
    settings: hou.FlipbookSettings, width: int, height: int
) -> None:
    _try_call(settings, "useResolution", True)
    _try_call(settings, "setUseResolution", True)
    _try_call(settings, "resolution", (width, height))
    _try_call(settings, "setResolution", (width, height))
    _try_call(settings, "outputZoom", 100)
    _try_call(settings, "setOutputZoom", 100)
    _try_call(settings, "useSheetSize", False)
    _try_call(settings, "setUseSheetSize", False)
    _try_call(settings, "cropOutMaskOverlay", True)
    _try_call(settings, "setCropOutMaskOverlay", True)
    _try_call(settings, "renderAllViewports", False)
    _try_call(settings, "setRenderAllViewports", False)


def _apply_flipbook_visibility(settings: hou.FlipbookSettings) -> None:
    flipbook_type = getattr(hou, "flipbookObjectType", None)
    if flipbook_type and hasattr(flipbook_type, "Visible"):
        _try_call(settings, "visibleTypes", flipbook_type.Visible)
        _try_call(settings, "setVisibleTypes", flipbook_type.Visible)

    _try_call(settings, "visibleObjects", ["*"])
    _try_call(settings, "setVisibleObjects", ["*"])


def _try_call(settings: hou.FlipbookSettings, method_name: str, arg: object) -> bool:
    if hasattr(settings, method_name):
        try:
            getattr(settings, method_name)(arg)
            return True
        except Exception:
            return False
    return False


def _try_set_flag(
    settings: hou.FlipbookSettings, value: bool, method_names: tuple[str, ...]
) -> bool:
    applied = False
    for method_name in method_names:
        if hasattr(settings, method_name):
            try:
                getattr(settings, method_name)(value)
                applied = True
            except TypeError:
                continue
    return applied


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


def _apply_viewport_overrides(
    viewport: hou.GeometryViewport,
) -> dict[str, object] | None:
    try:
        settings = viewport.settings()
    except Exception:
        log.warning("Could not access viewport settings to hide overlays.")
        return None

    state: dict[str, object] = {"settings": settings, "guides": {}}

    toggle_pairs = (
        ("showBadges", "showsBadges"),
        ("showName", "showsName"),
        ("showCameraName", "showsCameraName"),
        ("showStateStatus", "showsStateStatus"),
    )
    for getter, setter in toggle_pairs:
        previous = _get_viewport_value(settings, getter)
        if previous is not None:
            state[getter] = previous
            _set_viewport_value(settings, setter, False)

    display_ortho_grid = _get_viewport_value(settings, "displayOrthoGrid")
    if display_ortho_grid is not None:
        state["displayOrthoGrid"] = display_ortho_grid
        _set_viewport_value(settings, "setDisplayOrthoGrid", False)

    view_mask_opacity = _get_viewport_value(settings, "viewMaskOpacity")
    if view_mask_opacity is not None:
        state["viewMaskOpacity"] = view_mask_opacity
        _set_viewport_value(settings, "setViewMaskOpacity", 0.0)

    _apply_guide_visibility(settings, state)

    if hasattr(viewport, "setSettings"):
        try:
            viewport.setSettings(settings)
        except Exception:
            pass

    return state


def _restore_viewport_overrides(
    viewport: hou.GeometryViewport, state: dict[str, object] | None
) -> None:
    if not state:
        return
    settings = state.get("settings")
    if not isinstance(settings, hou.GeometryViewportSettings):
        return

    toggle_restore = (
        ("showBadges", "showsBadges"),
        ("showName", "showsName"),
        ("showCameraName", "showsCameraName"),
        ("showStateStatus", "showsStateStatus"),
    )
    for getter, setter in toggle_restore:
        if getter in state:
            _set_viewport_value(settings, setter, state[getter])

    if "displayOrthoGrid" in state:
        _set_viewport_value(settings, "setDisplayOrthoGrid", state["displayOrthoGrid"])

    if "viewMaskOpacity" in state:
        _set_viewport_value(settings, "setViewMaskOpacity", state["viewMaskOpacity"])

    _restore_guides(settings, state)

    if hasattr(viewport, "setSettings"):
        try:
            viewport.setSettings(settings)
        except Exception:
            pass


def _get_viewport_value(
    settings: hou.GeometryViewportSettings, method_name: str
) -> object | None:
    if hasattr(settings, method_name):
        try:
            return getattr(settings, method_name)()
        except Exception:
            return None
    return None


def _set_viewport_value(
    settings: hou.GeometryViewportSettings, method_name: str, value: object
) -> bool:
    if hasattr(settings, method_name):
        try:
            getattr(settings, method_name)(value)
            return True
        except Exception:
            return False
    return False


def _apply_guide_visibility(
    settings: hou.GeometryViewportSettings, state: dict[str, object]
) -> None:
    guide_enum = getattr(hou, "viewportGuide", None)
    if not guide_enum or not hasattr(settings, "enableGuide"):
        return
    if not hasattr(settings, "guideEnabled"):
        return

    guides_to_disable = {
        "CameraMask",
        "FieldGuide",
        "FillSelections",
        "FloatingGnomon",
        "FollowSelection",
        "GroupList",
        "IKCriticalZone",
        "NodeGuides",
        "NodeHandles",
        "ObjectNames",
        "ObjectPaths",
        "ObjectSelection",
        "OriginGnomon",
        "ParticleGnomon",
        "SafeArea",
        "ShowDrawTime",
        "ViewPivot",
        "XYPlane",
        "XZPlane",
        "YZPlane",
    }

    guides_state: dict[str, bool] = {}
    for name in dir(guide_enum):
        if name.startswith("_") or name not in guides_to_disable:
            continue
        guide = getattr(guide_enum, name)
        try:
            previous = settings.guideEnabled(guide)
        except Exception:
            continue
        guides_state[name] = bool(previous)
        try:
            settings.enableGuide(guide, False)
        except Exception:
            continue

    state["guides"] = guides_state


def _restore_guides(
    settings: hou.GeometryViewportSettings, state: dict[str, object]
) -> None:
    guide_enum = getattr(hou, "viewportGuide", None)
    guides_state = state.get("guides")
    if not guide_enum or not isinstance(guides_state, dict):
        return
    if not hasattr(settings, "enableGuide"):
        return

    for name, enabled in guides_state.items():
        if not hasattr(guide_enum, name):
            continue
        guide = getattr(guide_enum, name)
        try:
            settings.enableGuide(guide, bool(enabled))
        except Exception:
            continue


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
    try:
        scene_viewer.flipbook(viewport, settings, False)
    except Exception as exc:
        try:
            scene_viewer.flipbook(viewport, settings)
        except Exception:
            log.error("Flipbook failed: %s", exc, exc_info=True)
            raise
