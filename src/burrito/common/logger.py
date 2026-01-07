# burrito/common/logger.py
import logging
from uvicorn.logging import DefaultFormatter
import sys

class FastAPILogger:
    """Logger that mimics Uvicorn style and supports extra fields like log_id."""
    
    _initialized = {}

    @staticmethod
    def get_logger(name: str) -> logging.Logger:
        # avoid double initialization
        if name in FastAPILogger._initialized:
            return logging.getLogger(name)

        logger = logging.getLogger(name)
        logger.setLevel(logging.INFO)
        logger.propagate = False  # prevent double logs

        # create a stream handler that mimics Uvicorn style
        ch = logging.StreamHandler(sys.stdout)
        ch.setLevel(logging.INFO)

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
