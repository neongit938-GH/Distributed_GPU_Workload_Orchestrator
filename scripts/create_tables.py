import sys

from fairlane.db import engine
from fairlane.models import Base


if "--reset" in sys.argv:
    Base.metadata.drop_all(engine)

Base.metadata.create_all(engine)


