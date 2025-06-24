class ODM:
    def __init__(self, session):
        self.session = session

    def get_all(self, path):
        res = self.session.get(path)
        res.raise_for_status()
        return res.json()
    
    def get_one(self, path, id):
        res = self.session.get(f"{path}/{id}")
        res.raise_for_status()
        return res.json()
    
    def update_one(self, path, id, data):
        res = self.session.put(path=f"{path}/{id}", body=data)
        res.raise_for_status()
        return res.json()
    
    def add_one(self, path, data):
        res = self.session.post(path=path, body=data)
        res.raise_for_status()
        return res.json()

    def _exists(self, data, name):
        return next((obj.get("id") for obj in data if obj.get("name") == name), None)
