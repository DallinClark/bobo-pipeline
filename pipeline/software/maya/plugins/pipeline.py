from __future__ import annotations

import inspect
import logging
from pathlib import Path

from typing import TYPE_CHECKING, Any
from contextlib import contextmanager

from maya import cmds
from maya.api.OpenMaya import MObject
from pipe.m.command import get_registered_commands
from shared.util import get_repo_root

if TYPE_CHECKING:
    from pipe.m.command import CommandDescription
    from types import FunctionType

log = logging.getLogger("pipe.m.plugin")

PLUGIN_DISPLAY_NAME = "Sandwich Pipeline"
PLUGIN_NAME = "pipeline.py"
COMMAND_PREFIX = "SKD"
HOTKEY_SET_NAME = "Sandwich_Pipeline"
GITHUB_REPO_URL = (
    "https://github.com/joseph-wardle/sandwich-pipeline/tree/prod"  # base URL to repo
)
CUSTOM_HOTKEYS_TO_ADD: dict[str, str] = {"CreateMotionTrail": "ctrl+alt+m"}

maya_useNewAPI = True  # Tell Maya to use the Python API 2.0

REGISTERED_COMMANDS: list[str] = []


@contextmanager
def hotkey_set(name: str):
    """Context manager that creates a hotkeySet if it doesn't exist, sets it as current, and restores the previous set on exit."""
    prev_set: str = cmds.hotkeySet(query=True, current=True)  # type: ignore
    try:
        if cmds.hotkeySet(name, query=True, exists=True):
            cmds.hotkeySet(name, current=True)
        else:
            cmds.hotkeySet(name, edit=True, current=True)
        yield
    finally:
        cmds.hotkeySet(prev_set, edit=True, current=True)


def make_github_url(func: FunctionType) -> str | None:
    """
    Returns a GitHub URL pointing to the source file and line of the given function.
    """
    try:
        filepath_string = inspect.getsourcefile(func)
        if not filepath_string:
            return None
        filepath = Path(filepath_string)
        relative_path = filepath.relative_to(get_repo_root())
        source_lines, start_line_no = inspect.getsourcelines(func)
        start_line_no = inspect.getsourcelines(func)[1]
        end_line_no = start_line_no + len(source_lines) - 1
        url = f"{GITHUB_REPO_URL}/{relative_path}#L{start_line_no}-L{end_line_no}"
        return url
    except Exception:
        return None


def name_command_has_hotkey(name_command: str) -> bool:
    """Returns True if the given nameCommand has any hotkey bound to it."""
    try:
        key = cmds.hotkey(query=True, name=name_command)
        return bool(key)
    except RuntimeError:
        return False


def is_hotkey_assigned(key: str, ctrl=False, alt=False, shift=False) -> bool:
    """
    Returns True if the exact key combination (including modifiers) has a command assigned.
    """
    try:
        annotation = cmds.hotkeyCheck(
            keyString=key.upper() if shift else key,
            ctrlModifier=ctrl,
            altModifier=alt,
        )
        return bool(annotation)
    except RuntimeError:
        return False


def assign_hotkey(
    key: str,
    name_command: str,
    ctrl: bool = False,
    alt: bool = False,
    shift: bool = False,
    command_display_name: str | None = None,
    force=False,
):
    """
    Assigns a hotkey only if the key is not already bound.
    - key: key character (e.g., "d")
    - name_command: nameCommand to assign
    """
    if not force:
        if name_command_has_hotkey(name_command):
            return  # user has already customized this, don't touch it
        if is_hotkey_assigned(key, ctrl, alt, shift):
            mods = []
            if ctrl:
                mods.append("Ctrl")
            if alt:
                mods.append("Alt")
            if shift:
                mods.append("Shift")
            mods.append(key.upper())
            command_name_string = (
                command_display_name
                if command_display_name is not None
                else name_command
            )
            final_hotkey_string = "+".join(mods)

            log.debug(
                f' The pipeline command "{command_name_string}" has a default hotkey {final_hotkey_string},'
                "which was not applied as it is already assigned."
            )
            return  # the hotkey is assigned to something else

    cmds.hotkey(
        keyShortcut=key.upper() if shift else key,
        name=name_command,
        ctrlModifier=ctrl,
        altModifier=alt,
        shiftModifier=shift,
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


def add_named_command(command: str, label: str, hotkey: str | None = None):
    # Named Command (hotkeys)
    if hotkey is not None:
        named_command = f"{command}NamedCommand"
        cmds.nameCommand(
            named_command,
            command=command,  # type: ignore
            sourceType="mel",  # runtime commands are always invoked via MEL
            annotation=label,
        )
        if hotkey is not None:
            assign_hotkey_from_string(hotkey, named_command, label)


def register_command_from_description(command: CommandDescription):
    command_name = f"{COMMAND_PREFIX}_{command.name}"
    command_sub_category = (
        command.category.title().replace(" ", "")
        if command.category is not None
        else None
    )
    command_category = f"Pipeline{f'.{command_sub_category}' if command_sub_category is not None else ''}"

    module = command.function.__module__
    func_name = command.function.__name__

    runtime_command_optional_args: dict[str, Any] = {}
    if command.description:
        runtime_command_optional_args["annotation"] = command.description

    if command.icon:
        runtime_command_optional_args["image"] = command.icon

    if command.help_url:
        runtime_command_optional_args["helpUrl"] = command.help_url
    else:
        github_url = make_github_url(command.function)  # type: ignore
        if github_url is not None:
            runtime_command_optional_args["helpUrl"] = github_url

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
    add_named_command(command_name, command.label, command.hotkey)


# --- Standard Maya plug-in entry points ---
def initializePlugin(plugin: MObject) -> None:
    if not cmds.hotkeySet(HOTKEY_SET_NAME, query=True, exists=True):
        cmds.hotkeySet(HOTKEY_SET_NAME, current=True)
    else:
        cmds.hotkeySet(HOTKEY_SET_NAME, edit=True, current=True)

    for command in get_registered_commands():
        register_command_from_description(command)

    for command, hotkey in CUSTOM_HOTKEYS_TO_ADD.items():
        add_named_command(command, command, hotkey)

    log.info(f"{PLUGIN_DISPLAY_NAME} initialized")


def uninitializePlugin(plugin: MObject) -> None:
    for command in REGISTERED_COMMANDS:
        if cmds.runTimeCommand(command, exists=True):
            cmds.runTimeCommand(command, edit=True, delete=True)
    REGISTERED_COMMANDS.clear()
    log.info(f"{PLUGIN_DISPLAY_NAME} un-initialized")
