from datetime import datetime

def create_lead(lead: dict) -> dict:
    doc = {
        **lead,
        "created_at": datetime.utcnow()
    }

    res = client.index(
        index=INDEX_LEADS,
        document=doc,
        refresh=True
    )

    return {
        "id": res["_id"],
        "created_at": doc["created_at"]
    }
