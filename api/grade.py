import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from redpen.infrastructure.http import make_handler  # noqa: E402

_Base = make_handler("grade")


class handler(_Base):  # noqa: N801  (Vercel looks for a top-level "handler" class)
    pass
