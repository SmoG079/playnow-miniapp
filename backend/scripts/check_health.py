"""Check API, MySQL and authenticated Redis without logging credentials."""
import json
import os
import sys
import urllib.request

import redis
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url


def main():
    engine = None
    client = None
    try:
        with urllib.request.urlopen("http://127.0.0.1:8000/health", timeout=2) as response:
            if response.status != 200 or json.load(response).get("status") != "ok":
                raise RuntimeError("API is not healthy")
        engine = create_engine(make_url(os.environ["DATABASE_URL"]).set(drivername="mysql+pymysql"),
            connect_args={"connect_timeout": 2, "read_timeout": 2}, pool_pre_ping=True)
        with engine.connect() as connection:
            connection.execute(text("SELECT 1")).scalar_one()
        client = redis.Redis.from_url(os.environ["REDIS_URL"], socket_connect_timeout=2, socket_timeout=2)
        if not client.ping():
            raise RuntimeError("Redis is not healthy")
    except Exception as error:
        print(f"Health check failed: {type(error).__name__}", file=sys.stderr)
        return 1
    finally:
        if client is not None:
            client.close()
        if engine is not None:
            engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
