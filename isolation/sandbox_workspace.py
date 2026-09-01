import base64
import docker
import logging
import os
import posixpath
import shlex
from docker.errors import APIError
from typing import Optional, Sequence


class AgentSandbox:
    def __init__(
        self,
        image: str = "python:3.14-slim",
        scripts_dir: str = "isolation/scripts",
        default_timeout_seconds: int = 15,
        max_output_chars: int = 2000,
        allowed_commands: Optional[Sequence[str]] = None,
    ):
        self.client = docker.from_env()
        self.image = image
        self.container = None
        self.user = "65532:65532"
        self.workdir = "/workspace"
        self.scripts_dir = os.path.abspath(scripts_dir)
        self.scripts_mount = "/scripts"
        self.startup_mode = "uninitialized"
        self.default_timeout_seconds = max(1, int(default_timeout_seconds))
        self.max_output_chars = max(256, int(max_output_chars))
        self.allowed_commands = tuple(allowed_commands or ())

    def __enter__(self):
        """Starts the persistent background container when entering a 'with' block."""
        logging.info("Booting sandbox container...")

        if not os.path.isdir(self.scripts_dir):
            raise FileNotFoundError(f"Scripts directory does not exist: {self.scripts_dir}")

        startup_command = "bash -lc 'mkdir -p /workspace /tmp && tail -f /dev/null'"

        volumes = {
            self.scripts_dir: {"bind": self.scripts_mount, "mode": "ro"},
        }

        base_kwargs = {
            "command": startup_command,
            "detach": True,
            "network_mode": "none", # preferred over network_disabled=True
            "user": self.user,
            "working_dir": self.workdir,
            "read_only": True, # the agent cannot modify the container's filesystem (except for tmpfs at /workspace)
            "security_opt": ["no-new-privileges:true"],
            "cap_drop": ["ALL"],
            "tmpfs": {self.workdir: "rw,size=256m,nosuid,nodev,mode=1777"}, # in-memory (RAM) temporary file-system
            "volumes": volumes,
        }

        # size=256m maximum RAM that can be used
        # nosuid = no setuid. Cannot execute setuid binaries within the tmpfs.
        # nodev = do not interpret character or block special devices on the filesystem.
        # mode=1777 = sets the permissions to rwxrwxrwt (sticky bit set).

        strict_kwargs = {
            **base_kwargs,
            "mem_limit": "512m",  # Requires cgroup support on the host runtime.
            "pids_limit": 256,      # Requires cgroup support on the host runtime.
            # TODO: may want to limit the CPU as well (nano_cpus=1_000_000_000)
        }

        # Prefer strict limits; gracefully fall back when host Docker lacks cgroups.
        try:
            self.container = self.client.containers.run(self.image, **strict_kwargs)
            self.startup_mode = "strict"
        except APIError as exc:
            error_text = str(exc).lower()
            if "cgroup mountpoint does not exist" not in error_text and "cgroups" not in error_text:
                raise

            logging.warning(
                "Cgroup limits unavailable on this host runtime; starting sandbox "
                "without mem_limit/pids_limit. Error: %s",
                exc,
            )
            try:
                self.container = self.client.containers.run(self.image, **base_kwargs)
                self.startup_mode = "compatibility"
            except APIError as fallback_exc:
                fallback_text = str(fallback_exc).lower()
                if "cgroup mountpoint does not exist" in fallback_text or "cgroups" in fallback_text:
                    raise RuntimeError(
                        "Docker runtime cannot start containers on this host because cgroups are unavailable. "
                        "This is an environment issue, not a sandbox.py option issue. "
                        "Validate with: docker run --rm hello-world. "
                        "If that fails, fix Docker/cgroup setup (enable cgroup mounts, run Docker with systemd-managed daemon, "
                        "or use a runtime that supports cgroups on this host)."
                    ) from fallback_exc
                raise

        logging.info("Sandbox startup mode: %s", self.startup_mode)

        return self

    def _is_command_allowed(self, command: str) -> bool:
        if not self.allowed_commands:
            return True

        stripped = command.strip()
        return any(
            stripped == allowed or stripped.startswith(f"{allowed} ")
            for allowed in self.allowed_commands
        )

    def _truncate_output(self, output_text: str) -> str:
        if len(output_text) <= self.max_output_chars:
            return output_text
        return (
            output_text[: self.max_output_chars]
            + f"\n... [truncated to {self.max_output_chars} chars]"
        )

    def execute(self, command: str, timeout_seconds: Optional[int] = None) -> dict:
        """Injects a command into the running container."""
        if not self.container:
            raise RuntimeError("Sandbox is not running.")

        if not self._is_command_allowed(command):
            raise PermissionError("Command is not allowlisted for this sandbox.")

        effective_timeout = max(1, int(timeout_seconds or self.default_timeout_seconds))

        # Wrap in bash to support pipes (|), redirects (>), and chaining (&&)
        # Use timeout so hung commands do not consume turns indefinitely.
        wrapped_command = [
            "bash",
            "-lc",
            (
                f"cd {shlex.quote(self.workdir)} && "
                f"timeout --signal=KILL {effective_timeout}s "
                f"bash -lc {shlex.quote(command)}"
            ),
        ]

        logging.info(f"Executing: {command}")
        exit_code, output = self.container.exec_run(
            wrapped_command,
            user=self.user,
            workdir=self.workdir,
        )

        output_text = ""
        if isinstance(output, bytes):
            output_text = output.decode("utf-8", errors="replace").strip()
        elif isinstance(output, str):
            output_text = output.strip()

        output_text = self._truncate_output(output_text)
        timed_out = exit_code == 124

        return {
            "exit_code": exit_code,
            "output": output_text,
            "success": exit_code == 0,
            "timed_out": timed_out,
            "workdir": self.workdir,
            "scripts_dir": self.scripts_mount,
            "sandbox_mode": self.startup_mode,
        }

    # Note: the container is set to read-only everywhere, so this is more of a safety measure.
    def _resolve_within_workdir(self, path: str) -> str:
        # Treat path as relative to workdir and reject any traversal/absolute path that escapes it.
        normalized = posixpath.normpath(posixpath.join(self.workdir, path.lstrip("/")))
        if normalized != self.workdir and not normalized.startswith(self.workdir + "/"):
            raise PermissionError(f"Refusing to write outside the sandbox workdir: {path}")
        return normalized

    def write_file(self, path: str, content: str) -> dict:
        """Writes content to a file in the sandbox via base64 to avoid shell-quoting/escaping failures."""
        if not self.container:
            raise RuntimeError("Sandbox is not running.")

        resolved_path = self._resolve_within_workdir(path)
        encoded = base64.b64encode(content.encode("utf-8")).decode("ascii")
        command = f"base64 -d > {shlex.quote(resolved_path)} <<< {shlex.quote(encoded)}"
        return self.execute(command)

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Ensures the container is destroyed when the session ends or crashes."""
        if self.container:
            logging.info("Tearing down sandbox container...")
            # self.container.stop(timeout=2)  # Force fast stop
            # self.container.remove(force=True) 
            self.container = None



"""
import docker

client = docker.from_env()

client.containers.run(
    "your-agent-image:latest",
    # 1. Lock down the entire container OS layer
    read_only=True, 
    
    # 2. Carve out exactly one writable physical disk path
    volumes={
        '/absolute/path/on/host/sandbox': {
            'bind': self.workdir,
            'mode': 'rw' # Read-Write access explicitly for this folder
        }
    },
    
    # Optional: If the system/language runtimes require a small scratch space to boot
    tmpfs={
        '/tmp': 'rw,size=32m,nosuid,nodev'
    }
)
"""