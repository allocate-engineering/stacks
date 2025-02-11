import dbm


class SimpleDB:
    def __init__(self, filename: str):
        """
        Initialize the database connection.
        :param filename: The name of the file to store key-value pairs.
        """
        self.filename = filename

    def set(self, key: str, value: str):
        """
        Store a key-value pair in the database.
        :param key: The key to store.
        :param value: The value to store.
        """
        with dbm.open(self.filename, "c") as db:
            db[key] = value

    def get(self, key: str) -> str:
        """
        Retrieve a value from the database by key.
        :param key: The key to retrieve the value for.
        :return: The value associated with the key, or None if not found.
        """
        with dbm.open(self.filename, "c") as db:
            return db.get(key.encode("utf-8")).decode("utf-8") if key.encode("utf-8") in db else None

    def delete(self, key: str):
        """
        Delete a key-value pair from the database.
        :param key: The key to delete.
        """
        with dbm.open(self.filename, "c") as db:
            if key.encode("utf-8") in db:
                del db[key]

    def has_key(self, key: str):
        return key in self.keys()

    def keys(self) -> list:
        """
        Get all keys stored in the database.
        :return: A list of keys.
        """
        with dbm.open(self.filename, "c") as db:
            return [key.decode("utf-8") for key in db.keys()]

    def clear(self):
        """
        Clear all key-value pairs from the database.
        """
        with dbm.open(self.filename, "c") as db:
            pass  # Opening with 'n' mode automatically clears the database.
