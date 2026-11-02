import urllib.request
import json
import urllib.error

url = 'http://127.0.0.1:8000/api/staff/create/'
data = json.dumps({'username': 'testdoc99', 'password': 'password', 'name': 'Test Doc', 'role': 'Doctor'}).encode('utf-8')
req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})

try:
    response = urllib.request.urlopen(req)
    print("SUCCESS:", response.read().decode('utf-8'))
except urllib.error.HTTPError as e:
    print("ERROR", e.code, ":", e.read().decode('utf-8'))
except Exception as e:
    print("EXCEPTION:", str(e))
