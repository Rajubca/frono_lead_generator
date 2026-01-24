from datetime import datetime
from search.opensearch_client import client

INDEX = "frono_leads"


def create_lead(data: dict) -> dict:
    now = datetime.utcnow().isoformat()

    # Build dedup query
    should = []

    if data.get("email"):
        should.append({"term": {"email": data["email"]}})

    if data.get("phone"):
        should.append({"term": {"phone": data["phone"]}})

    # Search for existing lead
    existing = client.search(
        index=INDEX,
        body={
            "size": 1,
            "query": {
                "bool": {
                    "should": should,
                    "minimum_should_match": 1
                }
            }
        }
    )

    hits = existing["hits"]["hits"]

    # -----------------------------------
    # UPDATE EXISTING LEAD
    # -----------------------------------
    if hits:
        lead_id = hits[0]["_id"]
        old = hits[0]["_source"]

        updated_score = max(old.get("lead_score", 0), data["lead_score"])

        client.update(
            index=INDEX,
            id=lead_id,
            body={
                "doc": {
                    **data,
                    "lead_score": updated_score,
                    "updated_at": now
                }
            }
        )

        return {
            "id": lead_id,
            "created_at": old["created_at"]
        }

    # -----------------------------------
    # CREATE NEW LEAD
    # -----------------------------------
    data["created_at"] = now
    data["updated_at"] = now

    res = client.index(index=INDEX, body=data)

    return {
        "id": res["_id"],
        "created_at": now
    }
