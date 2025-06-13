import requests

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
