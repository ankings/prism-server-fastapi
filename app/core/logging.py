import sys
from pathlib import Path
from loguru import logger
from app.config import settings


def setup_logging() -> None:
    logger.remove()

    logger.add(
        sys.stderr,
        level=settings.log_level,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan> - <level>{message}</level>",
        colorize=True,
    )

    Path(settings.log_file).parent.mkdir(parents=True, exist_ok=True)
    logger.add(
        settings.log_file,
        level=settings.log_level,
        serialize=True,
        rotation="00:00",
        retention="30 days",
        compression="gz",
        enqueue=True,
    )
