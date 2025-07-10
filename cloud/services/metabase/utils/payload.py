class Payload:
    def __init__(self):
        self.payload = {}

    def set_attr(self, key, value):
        """
            Builds an attribute in the payload for Metabase components.
            :param key: The key of the attribute.
            :param value: The value of the attribute.
            :returns class object
        """
        if key and value:
            self.payload[key] = value
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
