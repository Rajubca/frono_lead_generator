import json
from search.opensearch_client import client

CONFIG_INDEX = "frono_configs"

# 1. Define your initial settings based on your current hardcoded values
initial_configs = [
    {"key": "bot_name", "value": "Frono Assistant"},
    {"key": "max_products_to_show", "value": 3},
    {"key": "safe_no_data_reply", "value": "I’m unable to find the right information for this at the moment. Please reach out to support@frono.uk."},
    {"key": "buying_points", "value": 20},
    {"key": "product_info_points", "value": 10},
    {"key": "closing_penalty", "value": -10},
    # Store complex patterns as JSON strings
    {"key": "collection_groups_json", "value": json.dumps({
        "Pest Control": ["Pest Control", "Garden Care", "Outdoor Products"],
        "Heaters": ["Heaters", "Winter Essentials", "Home Heating"],
        "Christmas Products": ["Christmas", "Christmas Lighting", "Christmas Costume"]
    })}
]

def init_admin():
    # Create index if it doesn't exist
    if not client.indices.exists(index=CONFIG_INDEX):
        client.indices.create(index=CONFIG_INDEX)
        print(f"Created index: {CONFIG_INDEX}")

    # Upload each config
    for config in initial_configs:
        client.index(
            index=CONFIG_INDEX,
            id=config["key"],
            body=config,
            refresh=True
        )
        print(f"Set {config['key']} default value.")

if __name__ == "__main__":
    init_admin()