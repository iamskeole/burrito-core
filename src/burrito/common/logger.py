import logging
import sys

from uvicorn.logging import DefaultFormatter

from burrito.common.config import settings


class FastAPILogger:
    _initialized = {}

    @staticmethod
    def get_logger(name: str) -> logging.Logger:
        # cleaner logs, in docker we'd have container name
        # and we don't need the prefixes, we can figure out where logs happen
        prefixes = [
            "burrito",
            "plugins",
            "handlers",
            "tools",
        ]
        for prefix in prefixes:
            name = name.replace(f"{prefix}.", "")

        # avoid double initialization
        if name in FastAPILogger._initialized:
            return logging.getLogger(name)

        level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
        logger = logging.getLogger(name)
        logger.setLevel(level)
        logger.propagate = False  # prevent double logs

        # create a stream handler that mimics uvicorn style
        ch = logging.StreamHandler(sys.stdout)
        ch.setLevel(level)

        class Formatter(DefaultFormatter):
            def format(self, record):
                log_id = getattr(record, "log_id", None)
                skip_name = getattr(record, "skip_module_name", False)
                if log_id:
                    if not skip_name:
                        record.msg = f"[{log_id} | {name}] {record.msg}"
                    else:
                        # minimal logging for end of generation messages
                        record.msg = f"[{log_id}] 🌯 {record.msg}"
                return super().format(record)

        ch.setFormatter(Formatter("%(levelprefix)s %(message)s"))
        logger.addHandler(ch)

        FastAPILogger._initialized[name] = True
        return logger
