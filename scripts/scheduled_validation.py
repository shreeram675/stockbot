import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.main import app


def main() -> None:
    client = TestClient(app)
    for path in [
        "/api/cron/daily-morning",
        "/api/cron/daily-close",
        "/api/cron/weekly",
        "/api/cron/monthly",
    ]:
        response = client.get(path)
        body = response.text[:300].replace("\n", " ")
        print(f"{path} status={response.status_code} body={body}")


if __name__ == "__main__":
    main()

