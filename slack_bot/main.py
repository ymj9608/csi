import asyncio

import uvicorn

from . import config, poller
from .interactions_server import app


async def main() -> None:
    server_config = uvicorn.Config(app, host="0.0.0.0", port=config.INTERACTIONS_PORT, log_level="info")
    server = uvicorn.Server(server_config)
    await asyncio.gather(poller.run_forever(), server.serve())


if __name__ == "__main__":
    asyncio.run(main())
