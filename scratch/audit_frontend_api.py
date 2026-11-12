import os, re, json

front_dir = 'ashdent-front/src'
api_calls = []

# Pattern to find API paths
api_regex = re.compile(r'[\'"`](/api/[^\'"`\s\?]+)[\'"`\?]')

for root, dirs, files in os.walk(front_dir):
    for f in files:
        if f.endswith(('.js', '.jsx', '.ts', '.tsx')):
            fpath = os.path.join(root, f)
            with open(fpath, 'r', encoding='utf-8', errors='ignore') as code_file:
                content = code_file.read()
                matches = api_regex.findall(content)
                for m in matches:
                    api_calls.append({
                        'file': os.path.relpath(fpath, 'ashdent-front'),
                        'endpoint': m
                    })

print(f"Total frontend API occurrences: {len(api_calls)}")

# Group by endpoint
endpoint_map = {}
for call in api_calls:
    ep = call['endpoint']
    # normalize param patterns like /api/patients/123/ -> /api/patients/:id/
    norm_ep = re.sub(r'/[0-9a-fA-F]{24}/?', '/:id/', ep)
    norm_ep = re.sub(r'/\$\{[^\}]+\}/?', '/:id/', norm_ep)
    if norm_ep not in endpoint_map:
        endpoint_map[norm_ep] = []
    endpoint_map[norm_ep].append(call['file'])

print(f"Unique frontend endpoints called: {len(endpoint_map)}")
for ep, files in sorted(endpoint_map.items()):
    print(f"  {ep} (used in {len(set(files))} files: {list(set(files))[:2]})")

with open('ashdent-back/scratch/audit6_frontend_endpoints.json', 'w') as f:
    json.dump(endpoint_map, f, indent=2)

