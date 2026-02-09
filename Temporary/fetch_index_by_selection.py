from opensearchpy import OpenSearch
import sys

# 1. Connect to OpenSearch
client = OpenSearch(
    hosts = [{'host': 'localhost', 'port': 9200}],
    http_compress = True,
    # http_auth = ('admin', 'admin'), # Uncomment and set if you have security enabled
    # use_ssl = True,
    # verify_certs = False,
)

def get_indices(client):
    """Fetches and displays available indices."""
    try:
        # Get all indices (format='json' makes it easier to parse)
        indices = client.cat.indices(format='json')
        
        # Filter out system indices (those starting with '.') if you want a cleaner list
        user_indices = [i['index'] for i in indices if not i['index'].startswith('.')]
        
        if not user_indices:
            print("No user indices found.")
            sys.exit()
            
        return user_indices
    except Exception as e:
        print(f"Error fetching indices: {e}")
        sys.exit()

def main():
    # --- Step 1: List Indices ---
    print("Fetching available indices...\n")
    available_indices = get_indices(client)

    print(f"{'ID':<5} {'Index Name'}")
    print("-" * 30)
    for idx, name in enumerate(available_indices):
        print(f"{idx:<5} {name}")
    print("-" * 30)

    # --- Step 2: User Selection ---
    while True:
        try:
            selection = int(input("\nEnter the ID of the index you want to view: "))
            if 0 <= selection < len(available_indices):
                selected_index = available_indices[selection]
                break
            else:
                print("Invalid ID. Please try again.")
        except ValueError:
            print("Please enter a valid number.")

    print(f"\nScanning index: '{selected_index}'...\n")

    # --- Step 3: Fetch and Display Data ---
    query = {
        "size": 100,  # Limit results (increase if needed)
        "query": {
            "match_all": {}
        }
    }

    try:
        response = client.search(body=query, index=selected_index)
        hits = response['hits']['hits']

        if not hits:
            print("Index is empty.")
        else:
            print(f"Found {len(hits)} documents:\n")
            for i, hit in enumerate(hits, 1):
                print(f"--- Document {i} ---")
                data = hit['_source']
                for key, value in data.items():
                    print(f"{key} : {value}")
                print("") # Empty line for separation

    except Exception as e:
        print(f"Error querying index: {e}")

if __name__ == "__main__":
    main()