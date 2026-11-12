import os, re, json

pattern = re.compile(r'API_BASE[^\n\r\'"`]*[\'"`]([^\'"\n\r`\?]+)[\'"`]|`\$\{API_BASE\}(/[^`\n\r\?]+)`')

calls = []
for root, dirs, files in os.walk('ashdent-front/src'):
    for f in files:
        if f.endswith(('.js', '.jsx', '.ts', '.tsx')):
            fpath = os.path.join(root, f)
            with open(fpath, 'r', encoding='utf-8', errors='ignore') as cf:
                c = cf.read()
                matches = pattern.findall(c)
                for m1, m2 in matches:
                    ep = m1 if m1 else m2
                    calls.append({
                        'file': os.path.relpath(fpath, 'ashdent-front'),
                        'endpoint': ep
                    })

print(f"Total API_BASE occurrences found: {len(calls)}")
unique_eps = sorted(set(c['endpoint'] for c in calls))
print(f"Unique endpoints called ({len(unique_eps)}):")
for ep in unique_eps:
    print(f"  {ep}")

with open('ashdent-back/scratch/frontend_endpoints_scanned.json', 'w') as f:
    json.dump(calls, f, indent=2)

