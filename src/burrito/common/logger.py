import logging
from uvicorn.logging import DefaultFormatter
import sys

from burrito.common.config import settings

class FastAPILogger:
    _initialized = {}

    @staticmethod
    def get_logger(name: str) -> logging.Logger:
        # avoid double initialization
        if name in FastAPILogger._initialized:
            return logging.getLogger(name)

        level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
        logger = logging.getLogger(name)
        logger.setLevel(level)
        logger.propagate = False  # prevent double logs

        # create a stream handler that mimics Uvicorn style
        ch = logging.StreamHandler(sys.stdout)
        ch.setLevel(level)

        class Formatter(DefaultFormatter):
            def format(self, record):
                log_id = getattr(record, "log_id", None)
                if log_id:
                    record.msg = f"[{log_id}] {record.msg}"
                return super().format(record)

        ch.setFormatter(Formatter("%(levelprefix)s %(message)s"))
        logger.addHandler(ch)

        FastAPILogger._initialized[name] = True
        return logger
