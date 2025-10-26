#!/usr/bin/env python3
"""
Graph MCP Server - 提供两数相加工具的 MCP 服务器
"""

import asyncio
import sys
from typing import Annotated
from pydantic import BaseModel, Field

from fastmcp import FastMCP
from loguru import logger
from rr_controller import RRController

logger.remove()
logger.add("server.log", level="DEBUG", format="{time:YYYY-MM-DD HH:mm:ss} {level} {file}:{line} {message}")
logger.add(sys.stderr, level="DEBUG", format="{time:YYYY-MM-DD HH:mm:ss} {level} {file}:{line} {message}")

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

    def run_cmd(self, cmd: str) -> str:
        if not self.rr_ctrl:
            return 'No replay session started'
        return self.rr_ctrl.run_cmd(cmd)

def create_server() -> FastMCP:
    logger.info(f'creating rr-mcp-server')
    server = RRMCPServer()

    @server.tool
    def rr_replay(rr_trace_dir: str) -> str:
        """
        Replay a trace using rr in directory `rr_trace_dir`.

        Args:
            rr_trace_dir: The directory containing the rr trace.

        Returns:
            str: empty string if successful, error message if error occurs.
        """
        return server.rr_replay(rr_trace_dir)

    @server.tool
    def run_cmd(self, cmd: str) -> str:
        """
        Run a gdb/rr command during a replay session.

        Args:
            cmd: The command to run.

        Returns:
            str: `cmd` executed result.
        """
        return server.run_cmd(cmd)

    return server

async def run():
    server = create_server()
    await server.run_http_async(
        host="0.0.0.0",
        port=8000,
        transport="http"
    )

if __name__ == "__main__":
    asyncio.run(run())
