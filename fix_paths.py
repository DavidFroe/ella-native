import json
import os

path = '/home/ella/.openclaw/agents/main/sessions/sessions.json'
with open(path, 'r') as f:
    content = f.read()

content = content.replace('/var/home/david/', '/home/ella/')
content = content.replace('/home/david/', '/home/ella/')

with open(path, 'w') as f:
    f.write(content)
print("Updated sessions.json successfully")
