from __future__ import annotations

import inspect
from dataclasses import dataclass
from types import FunctionType

REGISTERED_COMMANDS: list[CommandDescription] = []


@dataclass
class CommandDescription:
    function: FunctionType
    name: str
    label: str
    description: str | None = None
    category: str | None = None
    hotkey: str | None = None
    icon: str | None = None
    help_url: str | None = None


def register_maya_command(
    name: str,
    label: str,
    description: str | None = None,
    category: str | None = None,
    hotkey: str | None = None,
    icon: str | None = None,
    help_url: str | None = None,
):
    """
    Decorator that registers a python function as a Maya Command with optional keyboard shortcut and icon.
    Args:
        name: Unique internal command identifier.
        label: Human-readable command name for UI display.
        description: Optional description of the command. Defaults to the
            decorated function's docstring.
        category: Optional UI grouping or menu category.
        hotkey: Optional hotkey string for runtime command binding. (eg. ctrl+alt+b)
        icon: Optional icon name or file path for UI display.

    Returns:
        Callable: The original function, unchanged.
    """
    """

    """

    def decorator(func: FunctionType):
        resolved_description = (
            description if description is not None else inspect.getdoc(func)
        )
        command_description = CommandDescription(
            function=func,
            name=name,
            label=label,
            description=resolved_description,
            category=category,
            hotkey=hotkey,
            icon=icon,
            help_url=help_url,
        )
        global REGISTERED_COMMANDS
        REGISTERED_COMMANDS.append(command_description)
        return func

    return decorator


def get_registered_commands() -> list[CommandDescription]:
    return REGISTERED_COMMANDS
