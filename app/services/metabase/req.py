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
        res = requests.get(f"{self.base_url}/{path}", headers=self.headers)
        return res

    def post(self, path, body):
        res = requests.post(f"{self.base_url}/{path}", json=body, headers=self.headers)
        return res
