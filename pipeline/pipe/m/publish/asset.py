from __future__ import annotations

import hmac
import json
import logging
import os
import subprocess
from hashlib import sha1
from pathlib import Path
from typing import TYPE_CHECKING, cast
from urllib import request
from Qt.QtWidgets import QCheckBox, QWidget, QComboBox, QLabel, QHBoxLayout
from Qt.QtGui import QTextCursor, QRegExpValidator
from Qt.QtCore import QRegExp
from pipe.db import DB
from typing import Optional


if TYPE_CHECKING:
    from typing import Any, Sequence
from pipe.glui.dialogs import (
    FilteredListDialog,
    MessageDialog,
    MessageDialogCustomButtons,
)
from pipe.struct.db import Asset, SGEntity
from shared.util import get_pipe_path, get_production_path
from env import Executables, PIPEBOT_SECRET, PIPEBOT_URL

from software.houdini.dcc import HoudiniDCC
from .publisher import Publisher

try:
    from modelChecker.modelChecker_UI import UI as MCUI
except TypeError:
    # this external code throws errors when in headless mode
    MCUI = object

log = logging.getLogger(__name__)


ASSET_BUILDER_SCRIPT = get_pipe_path() / "pipe/h/assetbuilder.py"


class HoudiniBuildError(RuntimeError):
    """Raised when the Houdini asset build fails"""

    pass


class PublishAssetDialog(FilteredListDialog):
    _substance_only: QCheckBox
    _geo_var_widget: QWidget

    def __init__(
        self, parent: QWidget | None, items: Sequence[str], conn: Optional[DB]
    ) -> None:
        super().__init__(
            parent,
            items,
            "Publish Asset",
            "Select asset to publish",
            accept_button_name="Publish",
        )

        self._substance_only = QCheckBox(
            "Export Substance-only file? ONLY USE IF INSTRUCTED BY A LEAD"
        )
        self._layout.insertWidget(1, self._substance_only)

        self._conn = conn

        geo_var_widget = QWidget(self)
        geo_var_layout = QHBoxLayout(geo_var_widget)
        geo_var_layout.setContentsMargins(0, 0, 0, 0)
        geo_var_layout.setSpacing(0)
        geo_var_settings_widget = QWidget()
        geo_var_settings_layout = QHBoxLayout(geo_var_settings_widget)
        geo_var_label = QLabel("Geometry Variant:")
        geo_var_settings_layout.addWidget(geo_var_label, 30)

        # Editable combo box for geo variant
        self._geo_var_dropdown = QComboBox()
        self._geo_var_dropdown.setEditable(True)
        self._geo_var_dropdown.setCurrentText("default")
        pattern = QRegExp("[a-z][a-z_\d]*")
        geo_var_validator = QRegExpValidator(pattern)
        self._geo_var_dropdown.setValidator(geo_var_validator)
        geo_var_settings_layout.addWidget(self._geo_var_dropdown, 70)
        geo_var_layout.addWidget(geo_var_settings_widget, 90)
        self._layout.addWidget(geo_var_widget)

        self._populate_geo_var(None)

    def get_selected_variant(self) -> str:
        return self._geo_var_dropdown.currentText()

    @property
    def is_substance_only(self) -> bool:
        """Return whether the substance-only option is checked."""
        return self._substance_only.isChecked()

    def get_selected_item(self) -> str | None:
        selected_items = self._list_widget.selectedItems()
        if selected_items:
            return selected_items[0].text()
        return None

    def _on_item_selected(self) -> None:
        selected = self.get_selected_item()
        if self._conn and selected:
            asset = self._conn.get_asset_by_name(selected)
        else:
            return
        self._populate_geo_var(asset)

    def _populate_geo_var(self, asset: Asset | None) -> None:
        """Populate the variant selector with variants from the selected asset."""
        if asset and hasattr(asset, "geometry_variants"):
            var_set = set(asset.geometry_variants)
            var_set.add("main")
            variants = list(var_set)
        else:
            variants = []

        self._geo_var_dropdown.clear()
        self._geo_var_dropdown.addItems(variants)


class AssetPublisher(Publisher):
    _override: bool
    _geo_variant: str
    _is_substance_only: bool
    _component_export_dir: Path | None
    _component_hip_path: Path | None
    _component_basename: str | None
    _asset_pipe_name: str | None
    _houdini_error: str | None

    def __init__(self) -> None:
        super().__init__(PublishAssetDialog)
        self._geo_variant = "main"
        self._is_substance_only = False
        self._component_export_dir = None
        self._component_hip_path = None
        self._component_basename = None
        self._asset_pipe_name = None
        self._houdini_error = None

    @staticmethod
    def _compute_component_basename(
        asset: Asset, variant: str, is_substance: bool
    ) -> tuple[str, str]:
        pipe_name = (asset.name or "").strip()
        if not pipe_name or pipe_name.lower() == "none":
            pipe_name = (asset.disp_name or "").strip()
        if not pipe_name and asset.path:
            pipe_name = Path(asset.path).name
        if not pipe_name:
            pipe_name = "asset"

        base_name = pipe_name
        if variant and variant != "main":
            base_name = f"{base_name}_{variant}"
        if is_substance:
            base_name = f"{base_name}_SUBSTANCE"

        return pipe_name, base_name

    def _prepublish(self) -> bool:
        checker = ModelChecker.get()
        self._override = False
        if not checker.check_selected():
            checker_fail_dialog = MessageDialogCustomButtons(
                self._window,
                "Error. This asset did not pass the model checker. Please "
                "ensure your model meets the requirements set by the model "
                "checker.",
                "Cannot export: Model Checker",
                has_cancel_button=True,
                ok_name="Override",
                cancel_name="Ok",
            )
            self._override = bool(checker_fail_dialog.exec_())
            if not self._override:
                cursor = QTextCursor(checker.reportOutputUI.textCursor())
                cursor.setPosition(0)
                cursor.insertHtml(
                    "<h1>Asset not exported. Please resolve model checks.</h1>"
                )
                return False
        return True

    def _get_entity_list(self) -> list[str]:
        return self._conn.get_asset_name_list(sorted=True)

    def _get_entity_from_name(self, name: str) -> SGEntity | None:
        return self._conn.get_asset_by_name(name)

    def _get_save_path(self) -> Path | None:
        dialog = cast(PublishAssetDialog, self._dialog)
        asset = cast(Asset, self._entity)
        variant_name = dialog.get_selected_variant()
        try:
            assert asset.path is not None

            if not variant_name:
                raise ValueError()

        except AssertionError:
            error = MessageDialog(
                self._window,
                "Error: No path for this Asset set in ShotGrid. Nothing exported",
                "Error",
            )
            error.exec_()
            return None

        except ValueError:
            error = MessageDialog(
                self._window,
                "Error: No variant selected. Nothing exported,",
                "Error",
            )
            error.exec_()
            return None

        self._geo_variant = variant_name
        self._is_substance_only = dialog.is_substance_only
        self._component_export_dir = None
        self._component_hip_path = None
        self._asset_pipe_name = None
        self._houdini_error = None

        if variant_name not in asset.geometry_variants:
            asset.geometry_variants.add(variant_name)
            log.info(f"Updating new geo variant: {variant_name}")
            self._conn.update_asset(asset)

        pipe_name, basename = self._compute_component_basename(
            asset, variant_name, dialog.is_substance_only
        )
        publish_dir = get_production_path() / asset.path
        self._asset_pipe_name = pipe_name
        self._component_basename = basename
        return publish_dir / f"{basename}.usd"

    def _presave(self) -> bool:
        # notify webhook of override
        if self._override:
            asset = cast(Asset, self._entity)
            override_info = {
                "user": os.getlogin(),
                "asset": asset.disp_name,
                "path": str(self._publish_path),
            }
            data = bytes(json.dumps(override_info), encoding="utf-8")
            hashcheck = (
                "sha1=" + hmac.new(PIPEBOT_SECRET.encode(), data, sha1).hexdigest()
            )

            req = request.Request(
                url=PIPEBOT_URL + "/model_checker",
                data=data,
            )
            req.add_header("x-pipebot-signature", hashcheck)
            request.urlopen(req)
        return True

    def _get_mayausd_kwargs(self) -> dict[str, Any]:
        return {
            "shadingMode": "useRegistry",
        }

    def _postpublish(self) -> None:
        if self._is_substance_only:
            log.info("Skipping Houdini component publish for substance-only export")
            return

        asset = cast(Asset, self._entity)
        try:
            self._run_houdini_asset_builder(asset)
        except HoudiniBuildError as exc:
            self._houdini_error = str(exc)
            log.error("Houdini asset build failed: %s", exc, exc_info=True)
            MessageDialog(
                self._window,
                "Houdini component publish failed. Please review the Script Editor for details.",
                "Houdini Export Failed",
            ).exec_()
        else:
            self._houdini_error = None

    def _run_houdini_asset_builder(self, asset: Asset) -> None:
        publish_path = getattr(self, "_publish_path", None)
        if publish_path is None:
            raise HoudiniBuildError(
                "Publish path is undefined; cannot build Houdini component package."
            )

        publish_path = Path(publish_path)
        component_name = self._component_basename or publish_path.stem
        publish_dir = publish_path.parent
        export_dir = publish_dir / "export"
        hip_path = publish_dir / f"{component_name}.hipnc"

        self._component_export_dir = export_dir
        self._component_hip_path = hip_path

        if not ASSET_BUILDER_SCRIPT.exists():
            raise HoudiniBuildError(
                f"Unable to locate Houdini asset builder script: {ASSET_BUILDER_SCRIPT}"
            )

        if not Executables.hython.exists():
            raise HoudiniBuildError(
                f"Houdini executable not found at {Executables.hython}"
            )

        asset_pipe_name = (
            self._asset_pipe_name
            or (asset.name or "").strip()
            or (asset.disp_name or "").strip()
        )
        if not asset_pipe_name and asset.path:
            asset_pipe_name = Path(asset.path).name
        if not asset_pipe_name:
            asset_pipe_name = component_name

        command = [
            str(Executables.hython),
            "-m",
            "pipe.h.assetbuilder",
            "--hip-path",
            str(hip_path),
            "--usd-path",
            str(publish_path),
            "--export-dir",
            str(export_dir),
            "--component-name",
            component_name,
            "--asset-name",
            asset_pipe_name,
            "--variant",
            self._geo_variant,
            "--clean-export",
        ]

        if asset_pipe_name and asset_pipe_name != component_name:
            command.extend(["--root-prim", asset_pipe_name])

        dcc = HoudiniDCC(is_python_shell=True)
        env = dcc._get_env_vars()
        env["PIPE_LOG_LEVEL"] = str(log.getEffectiveLevel())

        log.info("Running Houdini asset builder for %s", component_name)
        try:
            result = subprocess.run(
                command,
                check=True,
                capture_output=True,
                text=True,
                env=env,
            )
        except FileNotFoundError as exc:
            raise HoudiniBuildError(
                "Failed to execute hython; verify Houdini is installed."
            ) from exc
        except subprocess.CalledProcessError as exc:
            stdout = exc.stdout or ""
            stderr = exc.stderr or ""
            if stdout:
                log.error("Houdini asset builder stdout:\n%s", stdout)
            if stderr:
                log.error("Houdini asset builder stderr:\n%s", stderr)
            raise HoudiniBuildError(
                f"Houdini component publish failed with exit code {exc.returncode}"
            ) from exc
        else:
            if result.stdout:
                log.debug("Houdini asset builder stdout:\n%s", result.stdout)
            if result.stderr:
                log.debug("Houdini asset builder stderr:\n%s", result.stderr)

        if not hip_path.exists():
            raise HoudiniBuildError(
                f"Houdini component build did not produce hip file at {hip_path}"
            )
        if not export_dir.exists():
            raise HoudiniBuildError(
                f"Houdini component build did not create export directory at {export_dir}"
            )

    def _get_confirm_message(self) -> str:
        message = super()._get_confirm_message()
        if self._is_substance_only:
            return message

        if self._houdini_error:
            return (
                f"{message}\n\nHoudini component publish failed: {self._houdini_error}"
            )

        extras: list[str] = []
        if self._component_hip_path:
            extras.append(f"Houdini scene: {self._component_hip_path}")
        if self._component_export_dir:
            extras.append(f"Houdini exports: {self._component_export_dir}")
        if extras:
            message = f"{message}\n\n" + "\n".join(extras)

        return message


class ModelChecker(MCUI):
    @classmethod
    def get(cls):
        if not cls.qmwInstance or (type(cls.qmwInstance) is not cls):
            cls.qmwInstance = cls()
        return cls.qmwInstance

    def configure(self) -> None:
        self.uncheckAll()
        commands = [
            # "crossBorder",
            "hardEdges",
            "lamina",
            # "missingUVs",
            "ngons",
            "noneManifoldEdges",
            # "onBorder",
            # "selfPenetratingUVs",
            "zeroAreaFaces",
            "zeroLengthEdges",
        ]
        for cmd in commands:
            self.commandCheckBox[cmd].setChecked(True)

    def check_selected(self) -> bool:
        self.configure()
        self.sanityCheck(["Selection"], True)
        self.createReport("Selection")

        # loop and show UI if anything had an error
        diagnostics = self.contexts["Selection"]["diagnostics"]
        for error in self.commandsList.keys():
            if (error in diagnostics) and len(self.parseErrors(diagnostics[error])):
                self.show_UI()
                return False

        return True

    # Override
    def sanityCheck(self, contextsUuids, refreshSelection=True) -> None:
        """The `sanityCheck` function cannot handle transforms that do not
        have children. This catches those errors and warns the modelers."""
        try:
            super().sanityCheck(contextsUuids, refreshSelection)
        except RuntimeError as err:
            if (
                "(kInvalidParameter): Object is incompatible with this method"
                in err.args
            ):
                MessageDialog(
                    self.parent(),
                    "The model checker could not run. Please ensure that you do "
                    "not have any empty transforms.",
                    "Model Checker Failed",
                ).exec_()
            else:
                raise err
