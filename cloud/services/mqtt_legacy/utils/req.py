import httpx

sensor_measurements_map = {
    "rg15": "Acc Rain",
    "si7021": "Humidity",
    "tmp1117": "Temperature",
    "ltr390": "UV Light",
    "pmsa003i": "Air Quality",
    "bme680": "Temperature",
}
headers = {"Content-Type": "application/json"}

class Req:
    @staticmethod
    async def insert(path: str, data):
        path = path if path.endswith('/') else path + '/'
        async with httpx.AsyncClient() as client:
            res = await client.post(path, json=data, headers=headers)

            if not (200 <= res.status_code < 300):
                return res.raise_for_status()
            return res.json()
        
    @staticmethod
    async def get_all(path: str):
        path = path if path.endswith('/') else path + '/'
        async with httpx.AsyncClient() as client:
            res = await client.get(path, headers=headers)

            if not (200 <= res.status_code < 300):
                res.raise_for_status()
            return res.json()
        
    @staticmethod
    async def update_one(path: str, data: dict):
        async with httpx.AsyncClient() as client:
            res = await client.put(path, json=data, headers=headers)

            if not (200 <= res.status_code < 300):
                res.raise_for_status()
            return res.json()
 
request = Req
