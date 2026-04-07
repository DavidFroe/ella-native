import pexpect
import sys
import time

child = pexpect.spawn('openclaw configure')
child.expect('Where will the Gateway run')
child.sendline('\n') # Local
child.expect('Select sections to configure')
# Navigate to Model
child.send('\x1b[B') # down
child.send(' ') # select space
child.sendline('\n') # submit

child.expect('Model/auth provider')
# Go up to Custom Provider (it's often near the top or bottom, type custom)
child.send('custom')
child.sendline('\n')

child.expect('API Base URL')
child.send('http://127.0.0.1:8081/v1')
child.sendline('\n')

child.expect('How do you want to provide this API key')
child.sendline('\n') # Paste API key now

child.expect('API Key')
child.sendline('\n') # leave blank

child.expect('Endpoint compatibility')
child.sendline('\n') # OpenAI-compatible

child.expect('Model ID')
child.send('auto')
child.sendline('\n')

child.expect('Endpoint ID', timeout=10)
child.sendline('\n') # accept default

time.sleep(1)
try:
    child.expect(pexpect.EOF, timeout=2)
except:
    pass
print("Done")
