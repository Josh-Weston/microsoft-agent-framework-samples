---
name: scripts
description: Provides access to various scripts for executing tasks within the sandbox environment. Use when asked to run or manage scripts.
license: Apache-2.0
compatibility: Requires python3
metadata:
  author: jweston
  version: "1.0"
---

# Scripts

Use this skill when a user asks to run or manage scripts within the sandbox environment. This skill is documentation only: its files are not the executable scripts. The executable scripts are mounted read-only at `/scripts` in the sandbox.

To run an inventory script, call the `execute_bash` tool with its documented command. Do not use a skill-provided script-execution tool or a path relative to this skill directory. Do not hallucinate script outputs; always execute the tool.

## Inventory

Each script entry describes when to use it, how to run it, what inputs it accepts, and what output to expect. Always execute the script; do not invent outputs.

### `hello_world.py`

- **Purpose**: Print a fixed hello-world message from the MAF workspace.
- **Use when**: The user asks to verify script execution or run a simple test script.
- **Path**: `/scripts/hello_world.py`
- **Command**:

  ```bash
  python /scripts/hello_world.py
  ```

- **Parameters**: None.
- **Output**: Writes one line to stdout:

  ```text
  Hello from a script in the MAF workspace
  ```

### `reverse_text.py`

- **Purpose**: Reverse a text string supplied on the command line.
- **Use when**: The user asks to reverse text.
- **Path**: `/scripts/reverse_text.py`
- **Command**:

  ```bash
  python /scripts/reverse_text.py "<text>"
  ```

- **Parameters**:

  | Name   | Required | Description                                        | Example         |
  | ------ | -------- | -------------------------------------------------- | --------------- |
  | `text` | Yes      | Text to reverse. Quote values that contain spaces. | `"hello world"` |

- **Output**: Writes the reversed text to stdout with a trailing newline.
- **Example**:

  ```bash
  python /scripts/reverse_text.py "hello world"
  ```

  Expected stdout:

  ```text
  dlrow olleh
  ```

### `check_calendar.py`

- **Purpose**: Return available calendar slots for scheduling.
- **Use when**: The user asks for available meeting times or to check availability.
- **Path**: `/scripts/check_calendar.py`
- **Command**:

  ```bash
  python /scripts/check_calendar.py [--date YYYY-MM-DD]
  ```

- **Parameters**:

  | Name     | Required | Description                                       |
  | -------- | -------- | ------------------------------------------------- |
  | `--date` | No       | Limits results to slots on the supplied ISO date. |

- **Output**: JSON with an `available_slots` array. Each slot provides ISO `start` and `end` times and an IANA `timezone`.
- **Example**:

  ```bash
  python /scripts/check_calendar.py --date 2026-09-08
  ```
