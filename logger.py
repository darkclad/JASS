"""Logging configuration for JASS application."""
import logging
import sys
from datetime import datetime

# Custom log levels for verbosity
# -d = WARNING (errors + warnings)
# -dd = INFO (+ info messages)
# -ddd = DEBUG (+ debug messages)
# -dddd = TRACE (+ trace messages - very verbose)
# -ddddd = ALL (everything including framework logs)

TRACE = 5  # Custom level below DEBUG
logging.addLevelName(TRACE, 'TRACE')


class JassLogger(logging.Logger):
    """Custom logger with TRACE level support."""

    def trace(self, msg, *args, **kwargs):
        if self.isEnabledFor(TRACE):
            self._log(TRACE, msg, args, **kwargs)


# Replace default logger class
logging.setLoggerClass(JassLogger)

# Create formatters
FORMATS = {
    'minimal': '%(message)s',
    'simple': '%(levelname)s: %(message)s',
    'standard': '%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    'detailed': '%(asctime)s [%(levelname)s] %(name)s (%(filename)s:%(lineno)d): %(message)s',
    'full': '%(asctime)s [%(levelname)s] %(name)s (%(filename)s:%(lineno)d) [%(funcName)s]: %(message)s',
}


def setup_logging(verbosity: int = 0) -> logging.Logger:
    """
    Configure logging based on verbosity level.

    Args:
        verbosity: Number of 'd' flags (0-5)
            0 = ERROR only
            1 = WARNING
            2 = INFO
            3 = DEBUG
            4 = TRACE
            5 = ALL (including third-party libs)

    Returns:
        Root logger for JASS
    """
    # Map verbosity to log level
    levels = {
        0: logging.ERROR,
        1: logging.WARNING,
        2: logging.INFO,
        3: logging.DEBUG,
        4: TRACE,
        5: TRACE,
    }

    # Map verbosity to format
    formats = {
        0: 'minimal',
        1: 'simple',
        2: 'standard',
        3: 'detailed',
        4: 'full',
        5: 'full',
    }

    level = levels.get(verbosity, logging.ERROR)
    fmt = FORMATS[formats.get(verbosity, 'minimal')]

    # Configure root logger for third-party libs
    if verbosity >= 5:
        # Enable all logging including third-party
        logging.basicConfig(
            level=level,
            format=fmt,
            datefmt='%Y-%m-%d %H:%M:%S',
            handlers=[logging.StreamHandler(sys.stderr)]
        )
    else:
        # Suppress third-party loggers
        logging.getLogger('urllib3').setLevel(logging.WARNING)
        logging.getLogger('requests').setLevel(logging.WARNING)
        logging.getLogger('werkzeug').setLevel(logging.WARNING if verbosity < 3 else logging.INFO)
        logging.getLogger('httpx').setLevel(logging.WARNING)
        logging.getLogger('httpcore').setLevel(logging.WARNING)
        logging.getLogger('openai').setLevel(logging.WARNING)
        logging.getLogger('anthropic').setLevel(logging.WARNING)

    # Create JASS logger
    logger = logging.getLogger('jass')
    logger.setLevel(level)

    # Remove existing handlers
    logger.handlers.clear()

    # Add console handler
    handler = logging.StreamHandler(sys.stderr)
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter(fmt, datefmt='%Y-%m-%d %H:%M:%S'))
    logger.addHandler(handler)

    # Log startup info
    if verbosity >= 2:
        logger.info(f"Logging initialized at level {logging.getLevelName(level)} (verbosity={verbosity})")

    return logger


def get_logger(name: str = None) -> logging.Logger:
    """
    Get a logger for a specific module.

    Args:
        name: Module name (will be prefixed with 'jass.')

    Returns:
        Logger instance
    """
    if name:
        return logging.getLogger(f'jass.{name}')
    return logging.getLogger('jass')


# Convenience function to log function entry/exit
def log_call(logger: logging.Logger):
    """Decorator to log function calls at TRACE level."""
    def decorator(func):
        def wrapper(*args, **kwargs):
            logger.log(TRACE, f">>> {func.__name__}() called")
            try:
                result = func(*args, **kwargs)
                logger.log(TRACE, f"<<< {func.__name__}() returned")
                return result
            except Exception as e:
                logger.error(f"!!! {func.__name__}() raised {type(e).__name__}: {e}")
                raise
        wrapper.__name__ = func.__name__
        return wrapper
    return decorator
