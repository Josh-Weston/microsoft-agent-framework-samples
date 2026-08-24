from sandbox import AgentSandbox


def run_agent_session():
    # 1. The 'with' statement automatically triggers __enter__() to boot the container
    with AgentSandbox(image="python:3.14-slim") as sandbox:
        print("Sandbox ready. Starting agent loop...\n")

        # --- Turn 1: Agent writes a file ---
        # The agent generates this bash command to create a python script
        setup_cmd = "echo 'print(\"Calculated: \", 10 * 5)' > math_script.py"
        result1 = sandbox.execute(setup_cmd)
        print(f"[Turn 1] Setup exit code: {result1['exit_code']}")

        # --- Turn 2: Agent checks if the file exists ---
        check_cmd = "ls -la"
        result2 = sandbox.execute(check_cmd)
        print(f"[Turn 2] Files:\n{result2['output']}\n")

        # --- Turn 3: Agent executes the script ---
        run_cmd = "python math_script.py"
        result3 = sandbox.execute(run_cmd)
        print(f"[Turn 3] Script output:\n{result3['output']}\n")

    # 2. When the block ends (or if an error is thrown), __exit__() automatically cleans up.
    print("Session ended. Sandbox destroyed.")


if __name__ == "__main__":
    run_agent_session()

