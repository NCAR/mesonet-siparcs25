import redis.asyncio as redis
from logger import CustomLogger

class RedisClient:
    def __init__(self, logger: CustomLogger, host: str, port: int):
        self.host = host
        self.port = port
        self.client = redis.Redis(host=host, port=port, decode_responses=True)
        self.logger = logger

    async def test_connection(self):
        """Test the connection to the Redis server asynchronously."""
        try:
            await self.client.ping()
            self.logger.log(f"Connected to Redis server successfully at {self.port}.")
        except redis.ConnectionError:
            self.logger.error(f"Failed to connect to Redis server at {self.port}.")
            exit(1)

    async def set(self, key: str, value: str):
        await self.client.set(key, value)

    async def hset(self, key: str, mapping: dict):
        await self.client.hset(key, mapping=mapping)

    async def get(self, key: str) -> str:
        return await self.client.get(key)

    async def hget(self, key: str, field: str) -> str:
        return await self.client.hget(key, field)

    async def expire(self, key: str, time_in_sec: int):
        await self.client.expire(key, time_in_sec)

    async def delete(self, key: str):
        await self.client.delete(key)

    async def exists(self, key: str) -> bool:
        return await self.client.exists(key) > 0
