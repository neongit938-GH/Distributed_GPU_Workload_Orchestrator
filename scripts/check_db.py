from sqlalchemy import text
from fairlane.db import engine


with engine.connect() as conn:
    result = conn.execute(text("SELECT version()"))
    print(result.scalar())