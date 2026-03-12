from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from maya import cmds
from maya.api.OpenMaya import MObject
from pipe.m.command import get_registered_commands

if TYPE_CHECKING:
    from pipe.m.command import CommandDescription

log = logging.getLogger("pipe.m.plugin")

PLUGIN_DISPLAY_NAME = "Sandwich Pipeline"
PLUGIN_NAME = "pipeline.py"
COMMAND_PREFIX = "SKD"

maya_useNewAPI = True  # Tell Maya to use the Python API 2.0

REGISTERED_COMMANDS: list[str] = []


def is_shortcut_assigned(key: str, ctrl=False, alt=False, shift=False) -> bool:
    """
    Returns True if the exact key combination (including modifiers) has a command assigned.
    """
    try:
        assigned = cmds.hotkey(
            key,
            query=True,
            name=True,
            ctrlModifier=ctrl,
            altModifier=alt,
            shiftModifier=shift,
        )
        return bool(assigned)  # empty string means unassigned
    except RuntimeError:
        return False


def assign_hotkey(
    key: str,
    name_command: str,
    ctrl: bool = False,
    alt: bool = False,
    shift: bool = False,
    command_display_name: str | None = None,
):
    """
    Assigns a hotkey only if the key is not already bound.
    - key: key character (e.g., "d")
    - name_command: nameCommand to assign
    """

    # Assign press name only if empty
    if not is_shortcut_assigned(key, ctrl, alt, shift):
        cmds.hotkey(
            keyShortcut=key,
            name=name_command,
            ctrlModifier=ctrl,
            altModifier=alt,
            shiftModifier=shift,
        )
    else:
        # 1. Generate the hotkey string if it wasn't provided

        mods = []
        if ctrl:
            mods.append("Ctrl")
        if alt:
            mods.append("Alt")
        if shift:
            mods.append("Shift")
        mods.append(key.upper())
        command_name_string = (
            command_display_name if command_display_name is not None else name_command
        )
        final_hotkey_string = "+".join(mods)

        log.debug(
            f' The pipeline command "{command_name_string}" has a default hotkey {final_hotkey_string},'
            "which was not applied as it is already assigned."
        )


def assign_hotkey_from_string(
    string: str,
    name_command: str,
    command_display_name: str | None = None,
):
    """
    Assigns a hotkey only if the key is not already bound.
    - string: the hotkey string (eg. ctrl+d)
    - name_command: nameCommand to assign
    """
    parts = [p.strip().lower() for p in string.split("+")]
    key = parts[-1]
    modifiers = parts[:-1]
    assign_hotkey(
        key,
        name_command,
        command_display_name=command_display_name,
        ctrl=any(m in ["ctrl", "ctl", "control"] for m in modifiers),
        alt="alt" in modifiers,
        shift="shift" in modifiers,
    )


def register_command_from_description(command: CommandDescription):
    command_name = f"{COMMAND_PREFIX}_{command.name}"

    command_category = f"pipeline{f'.{command.category.lower()}' if command.category is not None else ''}"

    module = command.function.__module__
    func_name = command.function.__name__

    runtime_command_optional_args: dict[str, Any] = {}
    if command.description is not None:
        runtime_command_optional_args["annotation"] = command.description

    if command.icon:
        runtime_command_optional_args["image"] = command.icon

    command_string = f"import {module}; {module}.{func_name}()"

    if cmds.runTimeCommand(command_name, exists=True):
        cmds.runTimeCommand(command_name, edit=True, delete=True)
    cmds.runTimeCommand(
        command_name,
        category=command_category,
        label=command.label,
        commandLanguage="python",
        command=command_string,  # type: ignore
        plugin="pipeline",
        default=False,
        **runtime_command_optional_args,  # type: ignore
    )
    REGISTERED_COMMANDS.append(command_name)

    # Named Command (hotkeys)
    if command.hotkey is not None:
        named_commmand = f"{command_name}NamedCommand"
        name_command_optional_args: dict[str, Any] = {}
        if command.description is not None:
            name_command_optional_args["annotation"] = command.description
        cmds.nameCommand(
            named_commmand,
            command=command_name,  # type: ignore
            sourceType="mel",  # runtime commands are always invoked via MEL
            annotation=command.description
            if command.description is not None
            else command.label,
        )
        if command.hotkey is not None:
            assign_hotkey_from_string(command.hotkey, named_commmand, command.label)


# --- Standard Maya plug-in entry points ---
def initializePlugin(plugin: MObject) -> None:
    for command in get_registered_commands():
        register_command_from_description(command)
    log.info(f"{PLUGIN_DISPLAY_NAME} initialized")


def uninitializePlugin(plugin: MObject) -> None:
    for command in REGISTERED_COMMANDS:
        if cmds.runTimeCommand(command, exists=True):
            cmds.runTimeCommand(command, edit=True, delete=True)
    REGISTERED_COMMANDS.clear()
    log.info(f"{PLUGIN_DISPLAY_NAME} un-initialized")
