import docker
import logging


class AgentSandbox:
    def __init__(self, image="python:3.11-slim"):
        self.client = docker.from_env()
        self.image = image
        self.container = None

    def __enter__(self):
        """Starts the persistent background container when entering a 'with' block."""
        logging.info("Booting sandbox container...")

        # We start the container once, keeping it alive indefinitely
        self.container = self.client.containers.run(
            self.image,
            command="tail -f /dev/null",  # The infinite sleep trick
            detach=True,
            mem_limit="512m",            # Strict memory cap
            network_disabled=True,       # Cut off internet for safety
            working_dir="/workspace"
        )
        return self

    def execute(self, command: str) -> dict:
        """Injects a command into the running container."""
        if not self.container:
            raise RuntimeError("Sandbox is not running.")

        # Wrap in bash to support pipes (|), redirects (>), and chaining (&&)
        # Using double quotes around the command requires escaping internal quotes,
        # so using a standard array format for exec_run is safer.
        wrapped_command = ["bash", "-c", command]

        logging.info(f"Executing: {command}")
        exit_code, output = self.container.exec_run(wrapped_command)

        return {
            "exit_code": exit_code,
            "output": output.decode('utf-8').strip(),
            "success": exit_code == 0
        }

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Ensures the container is destroyed when the session ends or crashes."""
        if self.container:
            logging.info("Tearing down sandbox container...")
            self.container.stop(timeout=2)  # Force fast stop
            self.container.remove(force=True)
