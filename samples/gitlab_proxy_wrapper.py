import sys
import subprocess
import time
import threading
import json

# Lock to prevent concurrent writes to stdout from pipe_stdin and pipe_stdout threads.
# Both threads can write (pipe_stdout for normal responses, pipe_stdin for intercepted ping replies),
# so we need to serialize their writes to avoid interleaved JSON-RPC messages.
_stdout_lock = threading.Lock()

def _write_stdout(data: bytes) -> None:
    with _stdout_lock:
        sys.stdout.buffer.write(data)
        sys.stdout.buffer.flush()

def main():
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

    # We pipe stdin/stdout for the framework, but send stderr straight to the console 
    # so we can see the connection logs without filling up hidden memory buffers
    process = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    if not process.stdout or not process.stderr or not process.stdin:
        print("Failed to open subprocess streams.")
        exit(1)

    # 2. Give the proxy 4.5 seconds to fully connect to GitLab
    time.sleep(4.5)

    with open("gitlab_proxy_wrapper.log", "a", encoding="utf-8") as log_file:
        log_file.write(f"Starting Node proxy with command: {' '.join(cmd)}\n")
        log_file.flush()

    # 3. Proxy is ready! Start piping the framework's data to Node, and Node's data to the framework
    def pipe_stdin():
        if not process.stdin:
            raise BrokenPipeError("Process stdin is not available")
        
        while True:
            line = sys.stdin.buffer.readline() # Bypasses the read-ahead buffer
            if not line:
                break

            # The agent framework (MCPStdioTool._ensure_connected) sends a 'ping' before every
            # tool/prompt listing call to verify the connection is still alive. GitLab's MCP
            # server does not implement the 'ping' method and returns -32601 (Method not found).
            # _ensure_connected treats ANY exception — including Method not found — as a
            # connection failure and triggers an infinite reconnect loop.
            # Fix: intercept ping requests here and reply with a valid empty result,
            # so the framework's connectivity check passes without involving GitLab.
            try:
                msg = json.loads(line.decode("utf-8", errors="replace").strip())
                method = msg.get("method")
                # GitLab's MCP server only advertises "tools" capability.
                # Intercept methods it doesn't support so the framework doesn't hang
                # waiting for a response that will never arrive (or get a -32601 error).
                if method in ("ping", "prompts/list", "resources/list"):
                    reply = json.dumps({
                        "jsonrpc": "2.0",
                        "id": msg.get("id"),
                        "result": {} if method == "ping" else {"prompts": []} if method == "prompts/list" else {"resources": []}
                    }) + "\n"
                    _write_stdout(reply.encode("utf-8"))
                    continue
            except Exception:
                pass
            
            with open("gitlab_proxy_wrapper.log", "a", encoding="utf-8") as log_file:
                log_file.write(f"To GitLab: {line.decode('utf-8', errors='replace')}")
                log_file.flush()

            process.stdin.write(line)
            process.stdin.flush()

    def pipe_stdout():
        if not process.stdout:
            raise BrokenPipeError("Process stdout is not available")
        
        while True:
            line = process.stdout.readline() # Bypasses the read-ahead buffer
            if not line:
                break
            with open("gitlab_proxy_wrapper.log", "a", encoding="utf-8") as log_file:
                log_file.write(f"From GitLab: {line.decode('utf-8', errors='replace')}")
                log_file.flush()
            _write_stdout(line)

    threading.Thread(target=pipe_stdin, daemon=True).start()
    threading.Thread(target=pipe_stdout, daemon=True).start()

    process.wait()

if __name__ == "__main__":
    main()