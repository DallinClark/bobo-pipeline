import logging

from Qt import QtGui
from Qt.QtWidgets import QPlainTextEdit, QWidget


class RigTestFormatter(logging.Formatter):
    """Custom formatter to prepends 'TEST:' to log messages."""

    def format(self, record: logging.LogRecord) -> str:
        # Get the base message from the logger
        message = record.getMessage()

        return f"TEST: {message}"


class QPlainTextEditLogHandler(logging.Handler):
    def __init__(self, text_edit: QPlainTextEdit):
        super().__init__()
        self.text_edit = text_edit

    def emit(self, record):
        msg = self.format(record)
        self.setFormatter(RigTestFormatter())
        # Use appendPlainText to keep it efficient
        try:
            self.text_edit.appendPlainText(msg)
            # Auto-scroll to bottom
            self.text_edit.moveCursor(QtGui.QTextCursor.End)
        except RuntimeError:
            self.close()


class RigBuildLogBox(QPlainTextEdit):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent=parent)
        self.setPlainText("Rig Build Log")
        self.setReadOnly(True)
        self.setMinimumSize(32, 24)
        self.log_handler = QPlainTextEditLogHandler(self)
        self._connected_loggers: list[logging.Logger] = []
        self.destroyed.connect(self._on_destroyed)

    def clear_log(self):
        self.clear()

    def connect_logger(self, logger: logging.Logger):
        logger.addHandler(self.log_handler)
        self._connected_loggers.append(logger)

    def disconnect_loggers(self):
        for logger in self._connected_loggers:
            logger.removeHandler(self.log_handler)
        self._connected_loggers.clear()

    def _on_destroyed(self):
        self.disconnect_loggers()
