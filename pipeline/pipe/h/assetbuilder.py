"""Build Houdini component packages for the Bobo asset pipeline."""

from __future__ import annotations

import argparse
import logging
import shutil
import sys
from pathlib import Path

import hou

from pipe.h import nodelayouts

log = logging.getLogger(__name__)


def _configure_logging(level: str) -> None:
    """Normalize CLI logging so build output stays predictable."""
    level_name = level.upper()
    numeric_level = getattr(logging, level_name, None)
    if not isinstance(numeric_level, int):
        numeric_level = logging.INFO
        log.warning("Unknown log level %s, defaulting to INFO", level)
    logging.basicConfig(
        level=numeric_level, format="[assetbuilder] %(levelname)s: %(message)s"
    )


def _set_parm(node: hou.Node, name: str, value) -> None:
    """Set a Houdini parameter and warn if templates drift from expectations."""
    parm = node.parm(name)
    if parm is None:
        log.warning("Parameter %s missing on %s", name, node.path())
        return
    parm.set(value)


def _prepare_stage() -> hou.Node:
    """Clear /stage so every package build starts from a clean LOP network."""
    stage = hou.node("/stage")
    if stage is None:
        raise RuntimeError(
            "Could not locate /stage context in the current Houdini session"
        )
    for child in stage.children():
        try:
            child.destroy()
        except hou.OperationFailed:
            log.warning(
                "Failed to destroy node %s while resetting /stage", child.path()
            )

    return stage


def _configure_component_geometry(geo_node: hou.LopNode, usd_path: Path) -> None:
    """Wire the imported USD into the component SOP net and promote preview nodes."""
    sopnet = geo_node.node("./sopnet/geo")
    if sopnet is None:
        raise RuntimeError("Component Geometry SOP network is missing")

    usd_import = sopnet.node("import_usd")
    if usd_import is None:
        raise RuntimeError("Template network is missing the import_usd node")
    _set_parm(usd_import, "filepath1", usd_path.as_posix())

    polyreduce = sopnet.node("polyreduce1")
    if polyreduce:
        # Keep the proxy reduction visible so artists land on performant geometry.
        if hasattr(polyreduce, "setDisplayFlag"):
            polyreduce.setDisplayFlag(True)
        if hasattr(polyreduce, "setRenderFlag"):
            polyreduce.setRenderFlag(True)
        try:
            polyreduce.setCurrent(True, clear_all_selected=False)
        except hou.OperationFailed:
            log.debug("Unable to set polyreduce node current; continuing")


def _execute_component_output(node: hou.Node) -> None:
    """Trigger the componentoutput node across Houdini versions."""
    previous_errors = tuple(node.errors())
    executed = False

    if isinstance(node, hou.RopNode):
        node.render()
        executed = True
    else:
        save_to_disk = getattr(node, "saveToDisk", None)
        if callable(save_to_disk):
            if not save_to_disk():
                raise RuntimeError("Component Output node failed to save to disk")
            executed = True
        else:
            for button in ("execute", "render", "renderbutton"):
                parm = node.parm(button)
                if parm is None:
                    continue
                parm.pressButton()
                executed = True
                break

    if not executed:
        raise RuntimeError(
            f"Component Output node {node.path()} has no supported execution parameter"
        )

    new_errors = [err for err in node.errors() if err not in previous_errors]
    if new_errors:
        joined = "; ".join(new_errors)
        raise RuntimeError(
            f"Component Output node {node.path()} reported errors: {joined}"
        )


def build_component_package(
    *,
    hip_path: Path,
    usd_path: Path,
    export_dir: Path,
    component_name: str,
    asset_name: str | None = None,
    root_prim: str | None = None,
    clean_export: bool = False,
) -> None:
    """Generate a Houdini component package network and write the exported USD.

    asset_name populates the ASSET context option so downstream tools can link
    the session back to the ShotGrid entity that initiated the publish.
    """
    usd_path = usd_path.resolve()
    if not usd_path.exists():
        raise FileNotFoundError(f"USD file not found: {usd_path}")

    hip_path = hip_path.resolve()
    hip_path.parent.mkdir(parents=True, exist_ok=True)

    export_dir = export_dir.resolve()
    if clean_export and export_dir.exists():
        log.info("Cleaning existing export directory: %s", export_dir)
        shutil.rmtree(export_dir)
    export_dir.mkdir(parents=True, exist_ok=True)

    log.info("Initializing new Houdini session at %s", hip_path)
    hou.hipFile.clear(suppress_save_prompt=True)
    hou.hipFile.save(str(hip_path))
    hou.setContextOption("ASSET", asset_name or component_name)

    stage = _prepare_stage()

    log.info("Building Bobo component network")
    component_out = stage.createNode("componentoutput", node_name="COMPONENT_OUT")
    component_out.setColor(hou.Color((0.616, 0.871, 0.769)))

    geo_node = nodelayouts.bobo_componentgeometry({}, parent=stage)
    if not isinstance(geo_node, hou.LopNode):
        raise RuntimeError("Component geometry network must be created inside LOPs")
    geo = geo_node
    cmat = nodelayouts.lnd_componentmaterial({}, parent=stage)
    lib = stage.createNode("dbclark::main::Bobo_MatLib")
    cnf = stage.createNode("sdm223::lnd_componentconfig")
    ldv = stage.createNode("sdm223::dev::LnD_Lookdev")
    env = stage.createNode("fetch")

    component_out.setInput(0, cnf)
    component_out.setInput(1, env)
    cnf.setInput(0, cmat)
    cmat.setInput(0, geo)
    cmat.setInput(1, lib)
    ldv.setInput(0, component_out)

    _set_parm(env, "loppath", f"../{ldv.name()}/OUT_ENV")

    component_out.moveToGoodPosition()
    for node in (geo, cmat, lib, cnf, ldv, env):
        node.moveToGoodPosition()

    if hasattr(component_out, "setDisplayFlag"):
        component_out.setDisplayFlag(True)
    if hasattr(geo, "setDisplayFlag"):
        geo.setDisplayFlag(True)

    _configure_component_geometry(geo, usd_path)

    component_out.setCurrent(True, clear_all_selected=True)

    root_name = root_prim or component_name
    _set_parm(component_out, "filename", component_name)
    _set_parm(component_out, "lopoutput", '$HIP/export/`chs("filename")`')
    _set_parm(component_out, "rootprim", f"/{root_name}")
    _set_parm(component_out, "localize", False)
    _set_parm(component_out, "thumbnailmode", 2)
    _set_parm(component_out, "renderer", "RenderMan RIS")
    _set_parm(component_out, "thumbnailscenesource", 1)
    _set_parm(component_out, "thumbnailinputcamera", "/lookdev/cam")

    log.info("Saving component package to %s", export_dir)
    _execute_component_output(component_out)

    hou.hipFile.save()
    log.info("Component package build complete")


def _parse_args(argv: list[str]) -> argparse.Namespace:
    """Translate CLI arguments into configuration for the asset builder."""
    parser = argparse.ArgumentParser(
        description="Build Houdini component package from Maya export"
    )
    parser.add_argument("--hip-path", required=True, help="Destination .hipnc path")
    parser.add_argument(
        "--usd-path", required=True, help="Source USD file exported from Maya"
    )
    parser.add_argument(
        "--export-dir",
        required=True,
        help="Directory where component USD layers will be written",
    )
    parser.add_argument(
        "--component-name",
        required=True,
        help="Component identifier used for filenames and root prim",
    )
    parser.add_argument(
        "--asset-name",
        help="Name stored on the ASSET context option for downstream tools",
    )
    parser.add_argument(
        "--root-prim", help="Optional override for the component root prim name"
    )
    parser.add_argument("--variant", help="Geometry variant name (for logging only)")
    parser.add_argument("--log-level", default="INFO", help="Python logging level")
    parser.add_argument(
        "--clean-export",
        action="store_true",
        help="Remove the export directory before writing new files",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Entrypoint for command-line execution."""
    args = _parse_args(argv or sys.argv[1:])
    _configure_logging(args.log_level)

    component_name = args.component_name
    if args.variant:
        log.info("Processing variant: %s", args.variant)

    try:
        build_component_package(
            hip_path=Path(args.hip_path),
            usd_path=Path(args.usd_path),
            export_dir=Path(args.export_dir),
            component_name=component_name,
            asset_name=args.asset_name,
            root_prim=args.root_prim,
            clean_export=args.clean_export,
        )
    except Exception as exc:  # noqa: BLE001
        log.exception("Failed to build component package: %s", exc)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
