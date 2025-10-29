#!/usr/bin/env python3
"""
Graph MCP Server - 提供两数相加工具的 MCP 服务器
"""

import asyncio
import sys, json
import loguru
from pydantic import BaseModel, Field

from fastmcp import FastMCP
from loguru import logger
from rr_controller import RRController

logger.remove()
logger.add("server.log", level="DEBUG", format="{time:YYYY-MM-DD HH:mm:ss} {level} {file}:{line} {message}")
logger.add(sys.stderr, level='INFO', format="{time:YYYY-MM-DD HH:mm:ss} {level} {file}:{line} {message}")

class ResultBase(BaseModel):
    succ: bool = Field(description='Whether the operation was successful', default=False)
    err_msg: str = Field(description='Error message if the operation failed', default='')

class RRReplayResult(ResultBase):
    result: str = Field(description='The result of the replay operation', default='')

class RunCmdResult(ResultBase):
    cmd: str = Field(description='The command that was executed')
    cmd_result: str = Field(description='The result of the command execution', default='')

class ReadFileResult(ResultBase):
    file_path: str = Field(description='The path to the file that was read')
    start_line: int = Field(description='The line number to start reading from')
    end_line: int = Field(description='The line number to stop reading at')
    content: str = Field(description='The content of the specified lines', default='')

class RRMCPServer(FastMCP):
    def __init__(self):
        super().__init__(
            name='rr-mcp-server',
            instructions='''
This is an MCP (Model Context Protocol) server that provides tools for controlling and interacting
with Mozilla's [rr](https://rr-project.org/) (record and replay) debugger. IT rovides the following
tools:
    1. replay a trace from a given directory
    2. run gdb/rr commands during a replay session
'''
        )
        self.rr_ctrl:RRController = None
        self.rr_trace_dir = None

    def rr_replay(self, rr_trace_dir: str) -> str:
        if self.rr_ctrl:
            logger.info(f'exiting previous replay session')
            self.rr_ctrl.exit()
        self.rr_trace_dir = rr_trace_dir
        logger.info(f'replaying trace in {rr_trace_dir}')
        self.rr_ctrl = RRController(rr_trace_dir)
        return f"Successfully started replay session for {rr_trace_dir}"

    def run_cmd(self, cmd: str) -> str:
        if not self.rr_ctrl:
            raise ValueError('No replay session started')
        rets = self.rr_ctrl.run_cmd_and_wait_stop(cmd)
        logger.info(f'run_cmd: {cmd} -> {rets}')
        return rets

def create_server() -> FastMCP:
    logger.info(f'creating rr-mcp-server')
    server = RRMCPServer()

    @server.tool
    def rr_replay(rr_trace_dir: str) -> RRReplayResult:
        """
        Replay a trace using rr in directory `rr_trace_dir`.

        Args:
            rr_trace_dir: The directory containing the rr trace.

        Returns:
            RRReplayResult: empty string if successful, error message if error occurs.
        """
        ret = RRReplayResult()
        try:
            ret.result = server.rr_replay(rr_trace_dir)
            ret.succ = True
        except Exception as e:
            ret.err_msg = str(e)

        return ret

    @server.tool
    def run_cmd(self, cmd: str) -> RunCmdResult:
        """
        Run a gdb/rr command during a replay session.

        Args:
            cmd: The command to run.

        Returns:
            str: `cmd` executed result.
        """
        ret = RunCmdResult(cmd=cmd)
        try:
            ret.cmd_result = server.run_cmd(cmd)
            ret.succ = True
        except Exception as e:
            ret.err_msg = str(e)

        return ret

    @server.tool
    def read_file(file_path: str, start_line: int, end_line: int) -> ReadFileResult:
        """
        Read a file and return the lines between start_line and end_line.

        Args:
            file_path: The path to the file to read.
            start_line: The line number to start reading from.
            end_line: The line number to stop reading at.
        
        Returns:
            ReadFileResult: The content of the specified lines, or error message if failed.
        """
        result = ReadFileResult(
            file_path=file_path,
            start_line=start_line,
            end_line=end_line,
        )

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            # Line numbers are 1-indexed
            if start_line < 1:
                result.err_msg = f"Error: start_line {start_line} must be >= 1."
                return result
            
            # Adjust end_line if it exceeds file length
            if end_line > len(lines):
                end_line = len(lines)
            
            if start_line > end_line:
                result.err_msg = f"Error: start_line {start_line} is greater than end_line {end_line}."
                return result
            
            # Extract lines (convert to 0-indexed)
            selected_lines = lines[start_line - 1:end_line]
            result.content = ''.join(selected_lines)
            result.succ = True
        except FileNotFoundError:
            result.err_msg = f"Error: File '{file_path}' not found."
        except PermissionError:
            result.err_msg = f"Error: Permission denied to read '{file_path}'."
            result.succ = False
        except Exception as e:
            result.err_msg = f"Error reading file '{file_path}': {str(e)}"
        return result

    return server

async def run():
    server = create_server()
    await server.run_http_async(
        host="0.0.0.0",
        port=8001,
        transport="http"
    )

if __name__ == "__main__":
    asyncio.run(run())
