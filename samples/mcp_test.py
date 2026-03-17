"""
This script proves that a handshake can be established with the GitLab MCP server using a manual payload.
If this script fails, the agent will also fail, so this is a good first step for debugging connection issues with GitLab.
"""

import subprocess
import json
import sys
import time
import threading

# Note: "npx" works directly in the shell because it resolves command names using the PATHEXT
npx = "npx.cmd" if sys.platform == "win32" else "npx"

cmd = [
    npx,
    "-y",
    "mcp-remote@latest",
    "https://gitlab.novascotia.ca/api/v4/mcp",
    "--static-oauth-client-metadata",
    '{"scope": "mcp"}',
]

# Note: This direct approach works as well
# cmd = [
#     "node",
#     r"C:\Users\JOSHUAS\AppData\Roaming\npm\node_modules\mcp-remote\dist\proxy.js",
#     "https://gitlab.novascotia.ca/api/v4/mcp",
#     "--static-oauth-client-metadata",
#     '{"scope": "mcp"}'
# ]

print("🔍 Launching Proxy and listening to logs...")
process = subprocess.Popen(
    cmd, 
    stdin=subprocess.PIPE, 
    stdout=subprocess.PIPE, 
    stderr=subprocess.PIPE, 
    text=True
)

if not process.stdout or not process.stderr or not process.stdin:
    print("Failed to open subprocess streams.")
    exit(1)

# Stream STDERR in the background so we can watch Node connect
def print_stderr():
    if process.stderr:
        for line in iter(process.stderr.readline, ''):
            print(f"[NODE] {line.strip()}")

threading.Thread(target=print_stderr, daemon=True).start()

print("⏳ Giving Node 4 seconds to fully establish the proxy to GitLab...")
time.sleep(4)

print("\n🤝 Proxy should be ready! Sending MCP Initialize request...")
handshake = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-06-18",
        "capabilities": {},
        "clientInfo": {"name": "debug-client", "version": "1.0.0"}
    }
}

# Send the payload to Node's standard input
process.stdin.write(json.dumps(handshake) + "\n")
process.stdin.flush()

print("📡 Request sent! Waiting for GitLab's response on STDOUT...")
print("(If it hangs here for more than 10 seconds, press Ctrl+C)\n")

# Block and wait for the server's reply
response = process.stdout.readline()

if response:
    print(f"🎉 SUCCESS! RESPONSE RECEIVED:\n{response}")
else:
    print("❌ No response received. The process closed silently.")

process.kill()