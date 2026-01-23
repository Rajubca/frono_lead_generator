from opensearchpy import OpenSearch

# Connect to OpenSearch
client = OpenSearch(
    hosts = [{'host': 'localhost', 'port': 9200}],
    http_compress = True,
    # Add auth if needed: http_auth = ('admin', 'admin')
)

query = {
    "size": 100,  # Number of results to return
    "query": {
        "match_all": {}
    }
}

response = client.search(body=query, index='frono_site_facts')

# Loop through hits and print Key:Value
for hit in response['hits']['hits']:
    print("-" * 30)
    data = hit['_source']
    for key, value in data.items():
        print(f"{key} : {value}")