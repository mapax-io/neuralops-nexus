"""
apps/core/logging_config.py

Console + rotating file logging for nexus-ai, mirroring nucleus's own
LOGGING setup in core/settings.py -- console stays available for
`docker logs`/stdout capture, the file exists so logs are readable
straight off disk too, e.g. via a mounted volume on the FAT image.
LOG_DIR defaults to a local "logs" directory; override via env var.
"""
import logging.config
import os
from pathlib import Path


def configure_logging() -> None:
    log_dir = Path(os.getenv("LOG_DIR", "logs"))
    log_dir.mkdir(parents=True, exist_ok=True)

    logging.config.dictConfig({
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "verbose": {
                "format": "%(asctime)s %(levelname)s %(name)s — %(message)s",
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "verbose",
            },
            "file": {
                "class": "logging.handlers.RotatingFileHandler",
                "filename": str(log_dir / "nexus-ai.log"),
                "maxBytes": 10 * 1024 * 1024,  # 10MB
                "backupCount": 5,
                "formatter": "verbose",
            },
        },
        "root": {
            "handlers": ["console", "file"],
            "level": os.getenv("LOG_LEVEL", "INFO"),
        },
    })
