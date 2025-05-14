import requests
import json

URL = "https://jsonplaceholder.typicode.com/todos/1"
resp = requests.get(URL)
print("Status:", resp.status_code)

try:
    data = resp.json()
    print("Response data:", json.dumps(data, indent=2))
except json.JSONDecodeError:
    print("Response is not valid JSON")
    print("Response text:", resp.text[:100])  # Show first 100 chars
