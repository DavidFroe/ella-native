import json, os
conf = os.path.expanduser('~/.config/openclaw-kibot/.openclaw/openclaw.json')
with open(conf) as f: data = json.load(f)

# Ensure models structure exists
if 'models' not in data: data['models'] = {}
if 'providers' not in data['models']: data['models']['providers'] = {}

# Use the EXACT structure from openclaw's official custom provider examples
data['models']['providers']['custom-localhost-8081'] = {
    'baseUrl': 'http://localhost:8081/v1',
    'models': ['auto']
}
with open(conf, 'w') as f: json.dump(data, f, indent=2)
