import json
from utils.session import Session
from utils.odm import ODM
from logger import CustomLogger

console = CustomLogger()

class Collection(ODM):
    def __init__(self, session: Session, name: str, description: str = None):
        super().__init__(session)
        self.name = name
        self.description = description
        self.path = "collection"

    def create(self) -> str:
        payload = {
            "name": self.name,
            "description": self.description
        }
        collections = self.get_all(self.path)
        collection_id = self._exists(collections, self.name)
        if collection_id is None:
            collection = self.add_one(self.path, payload)
            collection_id = collection.get("id")
            if collection_id:
                console.log(f"Collection: {self.name} is added successfully with ID: {collection_id}")
                return collection_id
            else:
                console.error(f"Failed to create collection: {self.name}")
                return "root"  # Default to root if creation fails
        else:
            console.log(f"Collection: {self.name} already exists with ID: {collection_id}")
            return collection_id
