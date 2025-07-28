from fastapi import Response
import requests
import httpx

class Req:
    def __init__(self, base_url):
        self.base_url = base_url
        self.headers = {
            "Content-Type": "application/json",
            "accept": "*/*"
        }

    # TODO: Use builder pattern for this

    def add_header(self, title, data):
        self.headers[title] = data

    def get(self, path):
        return requests.get(f"{self.base_url}/{path}", headers=self.headers)

    def post(self, path, body):
        return requests.post(f"{self.base_url}/{path}", json=body, headers=self.headers)
    
    def put(self, path, body):
        return requests.put(f"{self.base_url}/{path}", json=body, headers=self.headers)
    
    def delete(self, path):
        return requests.delete(f"{self.base_url}/{path}", headers=self.headers)

    async def post_async(self, path, body) -> Response:
        async with httpx.AsyncClient() as client:
            return await client.post(f"{self.base_url}/{path}", json=body, headers=self.headers)
        
    async def get_async(self, path):
        async with httpx.AsyncClient() as client:
            return await client.get(f"{self.base_url}/{path}", headers=self.headers)
    
    async def put_async(self, path, body):
        async with httpx.AsyncClient() as client:
            return await client.put(f"{self.base_url}/{path}", json=body, headers=self.headers)
