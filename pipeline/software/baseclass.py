from __future__ import annotations

import json
import logging
import os
import subprocess
import uuid
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import typing

from shared.util import fix_launcher_metadata

from .interface import DCCInterface, DCCLocalizerInterface

"""Baseclasses for interacting with DCCs"""

log = logging.getLogger(__name__)


class DCC(DCCInterface):
    command: str
    args: list[str] | None
    env_vars: typing.Mapping[str, int | str | None]
    pre_launch_tasks: typing.Callable[[], None]

    def __init__(
        self,
        command: str,
        args: typing.Sequence[str] | None = None,
        env_vars: typing.Mapping[str, int | str | None] | None = None,
        pre_launch_tasks: typing.Callable[[], None] | None = None,
    ) -> None:
        """Initialize DCC object.

        Keyword arguments:
        - command -- the command to launch the software
        - args    -- the arguments to pass to the command
        """

        if args is None:
            args = []

        self.command = command
        self.args = list(args) if args else None
        self.env_vars = env_vars or {}
        self.pre_launch_tasks = pre_launch_tasks or (lambda: None)

    def _get_env_vars(
        self, env_vars: typing.Mapping[str, int | str | None] | None = None
    ) -> dict[str, str]:
        """(Un)Set environment variables to their associated values.

        All values will be converted to strings. If a value is None,
        that environment variable will be unset.
        """
        BASE_ENVIRON = "BASE_ENVIRON"

        if BASE_ENVIRON not in os.environ:
            venv = os.environ.copy()
            venv[BASE_ENVIRON] = json.dumps(venv)
        else:
            venv = json.loads(os.environ[BASE_ENVIRON])

        if env_vars is None:
            env_vars = self.env_vars

        log.info("(Un)setting environment vars")

        for key, val in env_vars.items():
            if val is None:
                if key in venv:
                    del venv[key]
            else:
                venv[key] = str(val)

        PYTHONPATH = "PYTHONPATH"
        if PYTHONPATH not in venv:
            venv[PYTHONPATH] = ""

        print(venv[PYTHONPATH])
        return venv

    @staticmethod
    def _command_basename(command: str) -> str:
        normalized = str(command).strip().replace("\\", "/").rstrip("/")
        if not normalized:
            return "<empty>"
        return normalized.split("/")[-1] or "<empty>"

    def _launch_payload(
        self, command: str, args: typing.Sequence[str] | None
    ) -> dict[str, object]:
        return {
            "command_basename": self._command_basename(command),
            "arg_count": len(list(args or [])),
            "env_keys_set": sorted({str(key) for key in self.env_vars.keys()}),
        }

    def _emit_launch_event(
        self,
        *,
        status: str,
        action_id: str,
        payload: dict[str, object],
        error_message: str | None = None,
        exception_type: str | None = None,
    ) -> None:
        # Keep launch behavior independent from telemetry import/runtime issues.
        try:
            from pipe.telemetry import (
                STATUS_ERROR,
                STATUS_SUCCESS,
                emit,
                events,
                get_event_definition,
            )
        except Exception:
            log.debug("Telemetry import unavailable for dcc.launch", exc_info=True)
            return

        if status == "success":
            status_value = STATUS_SUCCESS
        else:
            status_value = STATUS_ERROR

        error_data = None
        if status == "error":
            event_definition = get_event_definition(events.EVENT_DCC_LAUNCH)
            error_code = (
                event_definition.error_codes[0]
                if event_definition.error_codes
                else "UNKNOWN_DCC_LAUNCH_ERROR"
            )
            error_data = {
                "code": error_code,
                "message": error_message or "Unknown DCC launch failure",
                "exception_type": exception_type,
            }

        emit(
            events.EVENT_DCC_LAUNCH,
            status=status_value,
            action_id=action_id,
            payload=payload,
            error=error_data,
        )

    def launch(
        self,
        command: str | None = None,
        args: typing.Sequence[str] | None = None,
        pre_launch_tasks: typing.Callable[[], None] | None = None,
    ) -> None:
        """Launch the software with the specified arguments.

        Passing in optional parameters will override their default
        values.
        """

        if command is None:
            command = self.command
        if args is None:
            args = self.args
        if pre_launch_tasks is None:
            pre_launch_tasks = self.pre_launch_tasks

        launch_action_id = str(uuid.uuid4())
        payload = self._launch_payload(command, args)

        try:
            fix_launcher_metadata()
            pre_launch_tasks()
            venv = self._get_env_vars()

            log.info("Launching the software")
            log.debug(f"Command: {command}, Args: {args}")
            return_code = subprocess.call([command] + list(args or []), env=venv)
        except Exception as exc:
            self._emit_launch_event(
                status="error",
                action_id=launch_action_id,
                payload=payload,
                error_message=str(exc),
                exception_type=type(exc).__name__,
            )
            raise

        if return_code == 0:
            self._emit_launch_event(
                status="success",
                action_id=launch_action_id,
                payload=payload,
            )
            return

        self._emit_launch_event(
            status="error",
            action_id=launch_action_id,
            payload=payload,
            error_message=f"DCC exited with return code {return_code}",
        )
        log.warning("DCC launch returned non-zero exit code: %s", return_code)


class DCCLocalizer(DCCLocalizerInterface):
    id: str

    def __init__(self, id: str) -> None:
        self.id = id
