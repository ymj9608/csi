import asyncio

import uvicorn

from . import config, poller
from .interactions_server import app


async def main() -> None:
    config.validate()
    if config.SLACK_MODE == 'socket':
        from .socket_mode import run_forever
        transport = run_forever()
    else:
        server_config = uvicorn.Config(app, host=config.INTERACTIONS_HOST, port=config.INTERACTIONS_PORT, log_level="info")
        transport = uvicorn.Server(server_config).serve()
    polling = asyncio.create_task(poller.run_forever())
    try:
        await transport
    finally:
        polling.cancel()
        await asyncio.gather(polling, return_exceptions=True)
        if poller._store is not None:
            poller._store.close()


if __name__ == "__main__":
    asyncio.run(main())
