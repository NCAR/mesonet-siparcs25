import json
from utils.session import Session
from utils.odm import ODM
from logger import CustomLogger

class Collection(ODM):
    def __init__(self, session: Session, logger: CustomLogger, name: str, description: str = None):
        super().__init__(session)
        self.console = logger
        self.console.debug(f"Initializing Collection with name: {name}")
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
                self.console.log(f"Collection: {self.name} is added successfully with ID: {collection_id}")
                return collection_id
            else:
                self.console.error(f"Failed to create collection: {self.name}")
                return "root"  # Default to root if creation fails
        else:
            self.console.log(f"Collection: {self.name} already exists with ID: {collection_id}")
            return collection_id
