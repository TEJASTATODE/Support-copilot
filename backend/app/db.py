"""Async Postgres connection pool with the pgvector type registered."""
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool
from pgvector.psycopg import register_vector_async

from app.config import settings

pool: AsyncConnectionPool | None = None


async def _configure(conn):
    await register_vector_async(conn)


async def init_db() -> AsyncConnectionPool:
    """Open the shared pool. Returns the pool instance."""
    global pool
    if pool is None:
        pool = AsyncConnectionPool(
            settings.database_url,
            configure=_configure,
            kwargs={"row_factory": dict_row},
            open=False,
            min_size=1,
            max_size=10,
        )
        await pool.open()
    return pool



async def close_db() -> None:
    global pool
    if pool is not None:
        await pool.close()
        pool = None

def get_pool() -> AsyncConnectionPool:
    """
    Get the shared pool. If not initialized (Windows subprocess race),
    raises a clear error. Use get_db dependency in endpoints instead.
    """
    if pool is None:
        raise RuntimeError("DB pool not initialised — call init_db() first")
    return pool


async def get_or_init_pool() -> AsyncConnectionPool:
    """
    Safe version — initializes if not ready.
    Used as fallback for Windows subprocess model.
    """
    global pool
    if pool is not None:
        return pool
    return await init_db()
