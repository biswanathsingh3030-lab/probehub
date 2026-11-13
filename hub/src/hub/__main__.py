"""Run the hub: `python -m hub`."""

import uvicorn

from hub.config import load_settings


def main() -> None:
    settings = load_settings()
    uvicorn.run("hub.main:app", host=settings.host, port=settings.port)


if __name__ == "__main__":
    main()
