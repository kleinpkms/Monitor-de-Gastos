import os

from motor.motor_asyncio import AsyncIOMotorClient

DB_NAME = os.environ.get("MONGODB_DB_NAME", "expense_tracker")

_client: AsyncIOMotorClient | None = None


def get_client() -> AsyncIOMotorClient:
    """Retorna um client Motor reutilizado entre invocações (importante em ambiente serverless,
    onde criar uma nova conexão a cada request esgotaria o pool do MongoDB)."""
    global _client
    if _client is None:
        uri = os.environ.get("MONGODB_URI")
        if not uri:
            raise RuntimeError("A variável de ambiente MONGODB_URI não está definida")
        _client = AsyncIOMotorClient(uri, maxPoolSize=10, tz_aware=True)
    return _client


def get_expenses_collection():
    return get_client()[DB_NAME]["expenses"]
