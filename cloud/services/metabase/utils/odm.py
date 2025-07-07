import requests
from utils.session import Session
from apis.users.types import APIResponse

class ODM:
    def __init__(self, session: Session):
        self.session = session

    def _exists(self, data, name):
        return next((obj.get("id") for obj in data if obj.get("name") == name), None)

    def get_all(self, path):
        res = self.session.get(path)
        if not (200 <= res.status_code < 300):
            res.raise_for_status()
            
        return res.json()
    
    def get_one(self, path, id):
        res = self.session.get(f"{path}/{id}")
        if not (200 <= res.status_code < 300):
            res.raise_for_status()
            
        return res.json()
    
    def update_one(self, path, id, data):
        res = self.session.put(path=f"{path}/{id}", body=data)

        if not (200 <= res.status_code < 300):
            res.raise_for_status()
            
        return res.json()
    
    def add_one(self, path, data):
        res = self.session.post(path=path, body=data)
        if not (200 <= res.status_code < 300):
            if res.status_code == 400:
                raise requests.exceptions.HTTPError(f"Bad Request: {res.text}")
            res.raise_for_status()
            
        return res.json()
    
    async def add_one_async(self, path, data) -> APIResponse :
        res = await self.session.post_async(path=path, body=data)
        if not (200 <= res.status_code < 300):
            if res.status_code == 400:
                raise requests.exceptions.HTTPError(f"Bad Request: {res.text}")
            res.raise_for_status()
            
        return {
            "message": "User added successfully.",
            "data": res.json(),
            "status": res.status_code
        }
    
    async def get_all_async(self, path):
        res = await self.session.get_async(path)
        if not (200 <= res.status_code < 300):
            res.raise_for_status() 
        if not res and not len(res):
            raise ValueError("No users found.")
            
        return {
            "message": "Users retrieved successfully.",
            "data": res.json()["data"],
            "status": res.status_code
        }
    
    async def update_async(self, path, data):
        res = await self.session.put_async(path=path, body=data)

        if not (200 <= res.status_code < 300):
            res.raise_for_status()
            
        return res.json()
