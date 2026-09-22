import asyncio
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from typing import Any, TypeVar


ResultT = TypeVar("ResultT")


async def run_in_thread(
    function: Callable[..., ResultT],
    /,
    *args: Any,
    **kwargs: Any,
) -> ResultT:
    """Run blocking work outside the event loop with deterministic cleanup."""
    loop = asyncio.get_running_loop()
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ownvitals")
    try:
        return await loop.run_in_executor(
            executor,
            partial(function, *args, **kwargs),
        )
    finally:
        executor.shutdown(wait=True, cancel_futures=True)
