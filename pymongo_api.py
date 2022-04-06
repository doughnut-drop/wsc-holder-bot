import os
import ssl
from pymongo import MongoClient
from typing import Union


class PyMongo:

    def __init__(self):
        self.MONGODB_PASSWORD = os.environ['MONGODB_PASSWORD']
        self.client = MongoClient(f'mongodb+srv://doughnut6716:{self.MONGODB_PASSWORD}@cluster0.f3nvm.mongodb.net/gas_tracker?retryWrites=true&w=majority', ssl_cert_reqs=ssl.CERT_NONE)

    def insert_data_into_collection(self, collection, data):
        if isinstance(data, dict):
            inserted = collection.insert_one(data)
            return str(inserted.inserted_id) + " document has been added"
        else:
            inserted = collection.insert_many(data)
            # Print a count of documents inserted.
            return str(len(inserted.inserted_ids)) + " documents inserted"

    def find_in_collection(self, collection, query: Union[list, dict], projection=None):
        return collection.find(query, projection)

    def delete_in_collection(self, collection, query: Union[list, dict], count):
        if count == 1:
            collection.delete_one(query)
        else:
            collection.delete_many(query)
