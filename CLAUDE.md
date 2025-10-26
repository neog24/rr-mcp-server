# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

This is an MCP (Model Context Protocol) server that provides tools for controlling and interacting with Mozilla's `rr` (record and replay) debugger. It allows clients to replay execution traces and run GDB commands during replay sessions through an HTTP interface.

## Core Architecture

### RRController (`rr_controller.py`)
- Extends `pygdbmi.GdbController` to control rr replay sessions
- Uses GDB/MI3 (Machine Interface) protocol to communicate with rr
- Key capabilities:
  - Starts rr replay sessions with `rr replay -i=mi`
  - Sends GDB commands and waits for responses
  - Parses GDB/MI responses (types: 'notify', 'stopped', etc.)
  - Manages async command/response cycles with timeout handling
- Response handling pattern: `_wait()` checks for specific (type, message) tuples to confirm command completion

### RRMcpServer (`rr_mcp_server.py`)
- Built on FastMCP framework
- Maintains singleton `RRController` instance per server
- Exposes two MCP tools:
  1. `rr_replay(rr_trace_dir)`: Start/restart replay session for a trace directory
  2. `run_cmd(cmd)`: Execute GDB/rr commands during active replay session
- Runs as HTTP server on `0.0.0.0:8000`

### State Management
- Server maintains single active replay session (`self.rr_ctrl`)
- Starting new replay automatically exits previous session
- Running commands without active session returns error

## Development Commands

### Running the server
```bash
# Development mode (direct execution)
python rr_mcp_server.py

# The server starts on http://0.0.0.0:8000
```

### Testing RRController standalone
```bash
# Use default trace location (~/.local/share/rr/latest-trace)
python rr_controller.py

# Use specific trace directory
python rr_controller.py /path/to/trace/dir
```

### Dependencies
```bash
# Install dependencies using uv
uv sync

# Or with pip
pip install -e .
```

## Key Technical Details

### GDB/MI Protocol
- Commands are sent as MI commands through `pygdbmi`
- Responses are JSON dictionaries with `type` and `message` fields
- Critical response types: `notify/stopped` indicates execution stopped

### Logging
- Uses `loguru` for structured logging
- Logs to both `server.log` and stderr
- Debug level enabled for detailed GDB/MI protocol inspection

### Trace Directory Structure
- Expects standard rr trace format (output of `rr record`)
- Default location: `~/.local/share/rr/latest-trace`
- Must contain rr's trace metadata and event log

## Important Patterns

When extending functionality:
- Use `_run_cmd_and_wait()` pattern for commands that should block until completion
- Check `self.rr_ctrl` existence before running commands
- Log responses at INFO level for debugging GDB/MI interactions
- Handle session cleanup with `exit()` before starting new sessions
