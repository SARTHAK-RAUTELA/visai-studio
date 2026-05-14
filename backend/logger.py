import logging
import sys


def _setup():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
        force=True,
    )


_setup()

logger = logging.getLogger("visai")
