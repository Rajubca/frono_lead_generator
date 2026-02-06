import time
import json
from search.opensearch_client import client

CONFIG_INDEX = "frono_configs"
def create_config_index():
    """Defines the schema and creates the index if it doesn't exist."""
    mapping = {
        "mappings": {
            "properties": {
                "key": {"type": "keyword"},
                "value": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
                "updated_at": {"type": "date", "format": "epoch_second"}
            }
        }
    }
    if not client.indices.exists(index=CONFIG_INDEX):
        client.indices.create(index=CONFIG_INDEX, body=mapping)
        print(f"✅ Created {CONFIG_INDEX} index.")
        
class ConfigManager:
    _cache = {}
    _last_sync = 0
    TTL = 60  # Sync settings every 60 seconds

    @classmethod
    def get_setting(cls, key, default=None):
        now = time.time()
        if not cls._cache or (now - cls._last_sync > cls.TTL):
            cls._refresh_cache()
        return cls._cache.get(key, default)

    @classmethod
    def _refresh_cache(cls):
        try:
            if not client.indices.exists(index=CONFIG_INDEX):
                return
            res = client.search(index=CONFIG_INDEX, body={"query": {"match_all": {}}, "size": 100})
            hits = res.get("hits", {}).get("hits", [])
            cls._cache = {h["_source"]["key"]: h["_source"]["value"] for h in hits}
            cls._last_sync = time.time()
        except Exception as e:
            print(f"Config sync error: {e}")