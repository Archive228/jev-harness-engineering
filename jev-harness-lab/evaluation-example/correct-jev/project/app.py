"""Tiny application: the backend supports both fields, the UI currently doesn't."""

ITEMS = [
    {"id": 1, "title": "Buy milk", "description": "Remember the blue carton"},
    {"id": 2, "title": "Prepare slides", "description": "Explain the export feature"},
]


def api_search(query, fields):
    query = query.casefold()
    return [item for item in ITEMS
            if any(query in item.get(field, "").casefold() for field in fields)]


def ui_request(query):
    return {"query": query, "fields": ["title", "description"]}


def search(query):
    request = ui_request(query)
    return api_search(request["query"], request["fields"])
