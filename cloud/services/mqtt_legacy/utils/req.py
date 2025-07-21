import httpx
import requests
from datetime import datetime

headers = {"Content-Type": "application/json"}

class Req:
    @staticmethod
    async def insert(path: str, data):
        path = path if path.endswith('/') else path + '/'

        if hasattr(data, "timestamp"):
            data = data.dict()
        
        if "timestamp" in data and isinstance(data["timestamp"], datetime):
            data["timestamp"] = data["timestamp"].isoformat()

        async with httpx.AsyncClient() as client:
            res = await client.post(path, json=data, headers=headers, timeout=60)

            if not (200 <= res.status_code < 300):
                return res.raise_for_status()
            return res.json()
        
    @staticmethod
    async def get_all(path: str):
        path = path if path.endswith('/') else path + '/'
        async with httpx.AsyncClient() as client:
            res = await client.get(path, headers=headers, timeout=60)

            if not (200 <= res.status_code < 300):
                res.raise_for_status()
            return res.json()
        
    @staticmethod
    async def update_one(path: str, data: dict):
        async with httpx.AsyncClient() as client:
            res = await client.put(path, json=data, headers=headers, timeout=60)

            if not (200 <= res.status_code < 300):
                res.raise_for_status()
            return res.json()
        
    @staticmethod
    def ping(path: str):
        return requests.get(path)

request = Req
