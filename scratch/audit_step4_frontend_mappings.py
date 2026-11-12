import os, re, json

front_dir = 'ashdent-front/src'
frontend_mappings = []

for root, dirs, files in os.walk(front_dir):
    for f in sorted(files):
        if f.endswith('.jsx') or f.endswith('.js'):
            p = os.path.join(root, f)
            with open(p, 'r', encoding='utf-8', errors='ignore') as file:
                content = file.read()
                
            # Find fetch calls
            # Matches fetch(`${API_BASE}/...`, { method: 'POST', ... })
            fetch_matches = re.finditer(r'fetch\s*\(\s*([`\'"][^`\'"]+[`\'"]|\$\{[^}]+\}[^`,\s)]*)', content)
            
            # Find API URLs in fetch
            calls = []
            for line in content.split('\n'):
                if 'fetch(' in line:
                    calls.append(line.strip())
                    
            if not calls and 'API_BASE' not in content and '/api/' not in content:
                continue
                
            # Extract endpoints
            endpoint_patterns = re.findall(r'[`\'"](?:\$\{API_BASE\}|http://127\.0\.0\.1:8000/api|/api)?(/[^`\'"?\s]+)[`\'"?]', content)
            
            # Extract methods
            methods = re.findall(r"method:\s*['\"](GET|POST|PUT|PATCH|DELETE)['\"]", content, re.IGNORECASE)
            methods = [m.upper() for m in methods] or ['GET']
            
            # Extract form inputs / fields submitted
            submitted_fields = re.findall(r'(?:body:\s*JSON\.stringify\(|\.post\(|\.put\()\{?([^})]+)\}?', content)
            clean_submitted = []
            for sf in submitted_fields:
                keys = re.findall(r'([A-Za-z0-9_]+):', sf)
                clean_submitted.extend(keys[:10])
                
            # Error handling
            has_error_catch = 'catch' in content or 'error' in content or 'toast' in content or 'Swal' in content
            
            frontend_mappings.append({
                'file_name': f,
                'file_path': p.replace('\\', '/'),
                'endpoints_called': sorted(list(set(endpoint_patterns))),
                'http_methods': sorted(list(set(methods))),
                'submitted_fields': sorted(list(set(clean_submitted)))[:15],
                'has_error_handling': has_error_catch,
                'sample_call': calls[0] if calls else ''
            })

out_path = 'ashdent-back/scratch/step4_frontend_mappings.json'
with open(out_path, 'w', encoding='utf-8') as f:
    json.dump(frontend_mappings, f, indent=2)

print(f"Frontend mapping complete! Analyzed {len(frontend_mappings)} components/files. Saved to {out_path}")

