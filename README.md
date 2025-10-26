# rr-mcp-server

An MCP (Model Context Protocol) server that provides tools for controlling and interacting with Mozilla's [rr](https://rr-project.org/) (record and replay) debugger. This enables AI assistants and other MCP clients to replay execution traces and run GDB commands programmatically.

## Features

- **Replay Management**: Start and manage rr replay sessions for recorded execution traces
- **GDB Command Execution**: Run arbitrary GDB/rr commands during replay sessions
- **HTTP Interface**: RESTful API for remote debugging control
- **Async Communication**: Robust async handling of GDB Machine Interface (MI) protocol
- **Session Management**: Automatic cleanup when switching between traces

## Prerequisites

- Python 3.12 or higher
- [rr debugger](https://rr-project.org/) installed and available in PATH
- Recorded execution traces (created with `rr record`)

## Installation

### Using uv (recommended)

```bash
uv sync
```

### Using pip

```bash
pip install -e .
```

## Usage

### Starting the Server

```bash
python rr_mcp_server.py
```

The server will start on `http://0.0.0.0:8000`.

### MCP Tools

The server exposes two tools through the MCP protocol:

#### 1. `rr_replay`

Start or restart a replay session for a given trace directory.

**Parameters:**
- `rr_trace_dir` (str): Path to the directory containing the rr trace

**Returns:**
- Empty string on success, error message on failure

**Example:**
```python
rr_replay("/home/user/.local/share/rr/my-trace")
```

#### 2. `run_cmd`

Execute a GDB/rr command during an active replay session.

**Parameters:**
- `cmd` (str): The GDB/rr command to execute

**Returns:**
- Command execution results as a string

**Example:**
```python
run_cmd("continue")
run_cmd("break main")
run_cmd("backtrace")
```

## How It Works

### Architecture

1. **RRController** (`rr_controller.py`): A wrapper around `pygdbmi.GdbController` that manages rr replay sessions and handles GDB/MI protocol communication
2. **RRMCPServer** (`rr_mcp_server.py`): A FastMCP-based server that exposes RRController functionality as MCP tools

### GDB Machine Interface

The server communicates with rr using the GDB Machine Interface (MI3) protocol, which provides structured, machine-parsable output. Responses are JSON objects with `type` and `message` fields.

### Session Lifecycle

1. Client calls `rr_replay` with a trace directory
2. Server starts `rr replay -i=mi` subprocess
3. Client can call `run_cmd` multiple times to interact with the replay
4. Starting a new replay automatically exits the previous session

## Recording Traces

Before using this server, you need to record execution traces with rr:

```bash
# Record a program
rr record ./your-program arg1 arg2

# The trace will be saved to ~/.local/share/rr/latest-trace
# or you can specify a custom location
```

## Logging

The server uses `loguru` for logging:
- Logs are written to `server.log` in the current directory
- Debug-level logs are also written to stderr
- GDB/MI protocol messages are logged for troubleshooting

## Example Workflow

```python
# 1. Start a replay session
rr_replay("~/.local/share/rr/my-app-trace")

# 2. Continue execution
run_cmd("continue")

# 3. Set a breakpoint
run_cmd("break some_function")

# 4. Continue to breakpoint
run_cmd("continue")

# 5. Inspect variables
run_cmd("print my_variable")

# 6. Get backtrace
run_cmd("backtrace")

# 7. Step through code
run_cmd("next")
run_cmd("step")

# 8. Reverse execution (rr's superpower!)
run_cmd("reverse-continue")
run_cmd("reverse-step")
```

## Use Cases

- **Automated Debugging**: Let AI assistants help debug recorded failures
- **Crash Analysis**: Programmatically analyze crashes in CI/CD pipelines
- **Test Debugging**: Automatically investigate flaky test failures
- **Remote Debugging**: Debug production recordings without manual GDB interaction

## Dependencies

- [fastmcp](https://github.com/jlowin/fastmcp) - MCP server framework
- [loguru](https://github.com/Delgan/loguru) - Logging
- [pydantic](https://docs.pydantic.dev/) - Data validation
- [pygdbmi](https://github.com/cs01/pygdbmi) - GDB Machine Interface communication
