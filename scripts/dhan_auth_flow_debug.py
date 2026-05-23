import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.dhan_auth import DhanAuthService


async def main() -> None:
    consent = await DhanAuthService().generate_consent()
    print("consent_id_present=", bool(consent.get("consent_id")))
    print("login_url=", consent.get("login_url"))


if __name__ == "__main__":
    asyncio.run(main())

