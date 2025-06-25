class Payload:
    def __init__(self):
        self.payload = {}

    def name(self, name: str):
        """
        Builds the name payload for Metabase components.
        :param name: The name of the component.
        """
        if name:
            self.payload["name"] = name
        return self
    
    def description(self, description: str):
        """
        Builds the description payload for Metabase components.
        :param description: The description of the component.
        """
        if description:
            self.payload["description"] = description
        return self
    
    def parent_id(self, parent_id: str):
        """
        Builds the parent_id payload for Metabase components.
        :param parent_id: The ID of the parent component.
        """
        if parent_id:
            self.payload["parent_id"] = parent_id
        return self
    
    def build(self):
        """
        Builds the final payload for Metabase components.
        :return: The constructed payload dictionary.
        """
        return self.payload if self.payload else None

    def reset(self):
        """
        Resets the payload to an empty state.
        """
        self.payload = {}
        return self
