"""Cria os indices recomendados na colecao `expenses`.

Uso: python scripts/create_indexes.py
Requer a variavel de ambiente MONGODB_URI (pode vir de um arquivo .env na raiz).
"""
import os

from dotenv import load_dotenv
from pymongo import ASCENDING, DESCENDING, MongoClient

load_dotenv()

MONGODB_URI = os.environ["MONGODB_URI"]
DB_NAME = os.environ.get("MONGODB_DB_NAME", "expense_tracker")


def main() -> None:
    client = MongoClient(MONGODB_URI)
    collection = client[DB_NAME]["expenses"]

    collection.create_index([("date", DESCENDING)], name="date_desc")
    collection.create_index([("category", ASCENDING)], name="category_asc")
    collection.create_index([("tags", ASCENDING)], name="tags_asc")
    collection.create_index([("date", DESCENDING), ("category", ASCENDING)], name="date_category")

    print(f"Indices criados na colecao '{DB_NAME}.expenses':")
    for name in collection.index_information():
        print(f"  - {name}")


if __name__ == "__main__":
    main()
