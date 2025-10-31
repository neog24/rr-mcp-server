import os
import sys
import subprocess
import time
from typing import Optional
from loguru import logger
import lldb


class LLDBRRController:
    """Controller for rr replay sessions using LLDB as the debugger."""

    def __init__(self, trace_dir: str, port: int = 50505):
        """
        Initialize LLDB controller for rr replay.

        Args:
            trace_dir: Path to rr trace directory
            port: Port number for rr gdbserver (default: 50505)
        """
        self.trace_dir = trace_dir
        self.port = port
        self.debugger: Optional[lldb.SBDebugger] = None
        self.target: Optional[lldb.SBTarget] = None
        self.process: Optional[lldb.SBProcess] = None
        self.rr_process: Optional[subprocess.Popen] = None
        self.exe_path: Optional[str] = None

        # Initialize LLDB
        lldb.SBDebugger.Initialize()
        self.debugger = lldb.SBDebugger.Create()

        if not self.debugger or not self.debugger.IsValid():
            raise RuntimeError("Failed to create LLDB debugger")

        # Set synchronous mode - commands will block until completion
        # This means we don't need to manually wait for events
        self.debugger.SetAsync(False)

        # Enable verbose output for better debugging
        self.debugger.SetOutputFileHandle(sys.stdout, False)
        self.debugger.SetErrorFileHandle(sys.stderr, False)

        logger.info(f"Initialized LLDB debugger (version: {lldb.SBDebugger.GetVersionString()})")
        logger.info(f"Starting rr replay as gdbserver on port {self.port}")

        # Start rr replay as a gdbserver
        self.rr_process = subprocess.Popen(
            ['rr', 'replay', '-s', str(self.port), trace_dir],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1
        )

        # Wait for gdbserver to start
        logger.info("Waiting for rr gdbserver to start...")
        time.sleep(2)

        # Check if rr process is still running
        if self.rr_process.poll() is not None:
            stdout_data = self.rr_process.stdout.read() if self.rr_process.stdout else ""
            stderr_data = self.rr_process.stderr.read() if self.rr_process.stderr else ""
            raise RuntimeError(
                f"rr replay failed to start.\nStdout: {stdout_data}\nStderr: {stderr_data}"
            )

        logger.info("rr gdbserver started successfully")

        # Get the executable path from the trace
        # self.exe_path = '/home/vince.wu/src/rr-mcp-server/crash'
        self.exe_path = self._get_exe_path_from_trace()
        if self.exe_path:
            logger.info(f"Found executable in trace: {self.exe_path}")
        else:
            logger.warning("Could not determine executable path from trace")

        # Connect LLDB to the gdbserver
        self._connect_to_rr()

        logger.info("LLDB controller initialized and connected to rr replay")

    def _get_exe_path_from_trace(self) -> Optional[str]:
        """
        Extract the executable path from the rr trace directory.

        Returns:
            Optional[str]: Path to the executable, or None if not found
        """
        try:
            # Method 1: Use 'rr ps' command to get process info
            # This is the most reliable method as it directly queries rr's metadata
            result = subprocess.run(
                ['rr', 'ps', self.trace_dir],
                capture_output=True,
                text=True,
                timeout=5
            )

            if result.returncode == 0:
                # Parse the output to get the executable path
                # Format: PID    PPID    EXIT    CMD
                lines = result.stdout.strip().split('\n')
                if len(lines) > 1:  # Skip header
                    # Get the first process (main process)
                    process_line = lines[1]
                    # The CMD column contains the full command line
                    # Split by tabs/spaces and get the executable path
                    parts = process_line.split()
                    if len(parts) >= 4:
                        # The 4th column onwards is the CMD
                        cmd = ' '.join(parts[3:])
                        # Extract the executable path (first part of the command)
                        exe_path = cmd.split()[0]

                        # Verify it's a valid file
                        if os.path.isfile(exe_path):
                            logger.debug(f"Found executable via 'rr ps': {exe_path}")
                            return exe_path
                        else:
                            logger.debug(f"Executable from 'rr ps' not found on filesystem: {exe_path}")

            # Method 2: Check for the 'exe' symlink in trace directory (newer rr versions)
            exe_link = os.path.join(self.trace_dir, 'exe')
            if os.path.exists(exe_link):
                exe_path = os.readlink(exe_link) if os.path.islink(exe_link) else exe_link
                if os.path.isfile(exe_path):
                    logger.debug(f"Found executable via exe link: {exe_path}")
                    return exe_path

            # Method 3: Read from the mmap file (fallback for older traces)
            trace_info_path = os.path.join(self.trace_dir, 'mmap')
            if os.path.exists(trace_info_path):
                # Parse mmap file to find the executable
                with open(trace_info_path, 'rb') as f:
                    # The mmap file is binary, but we can try to extract the path
                    content = f.read(4096)  # Read first 4KB
                    # Look for ELF executable paths (they often start with /)
                    import re
                    paths = re.findall(b'/[^\x00]+', content)
                    for path in paths:
                        try:
                            path_str = path.decode('utf-8', errors='ignore')
                            # Check if it's a valid executable file
                            if os.path.isfile(path_str) and os.access(path_str, os.X_OK):
                                # Skip common libraries
                                if not any(lib in path_str for lib in ['/lib/', '/usr/lib/', '.so']):
                                    logger.debug(f"Found potential executable: {path_str}")
                                    return path_str
                        except:
                            continue

        except subprocess.TimeoutExpired:
            logger.debug("Timeout running 'rr ps' command")
        except Exception as e:
            logger.debug(f"Error getting executable path from trace: {e}")

        return None

    def _connect_to_rr(self):
        """Connect LLDB to the rr gdbserver."""
        logger.info(f"Connecting LLDB to rr gdbserver at localhost:{self.port}")

        # Create a target with the executable if we found it
        target_path = self.exe_path if self.exe_path else ""
        error = lldb.SBError()

        logger.debug(f"Creating target with executable: {target_path or '(empty)'}")
        self.target = self.debugger.CreateTarget(target_path, None, None, True, error)

        if error.Fail():
            logger.warning(f"Warning creating target: {error.GetCString()}")
            # Try without executable path
            self.target = self.debugger.CreateTarget("")

        if not self.target or not self.target.IsValid():
            self._cleanup()
            raise RuntimeError("Failed to create LLDB target")

        # Connect to the remote gdb server using command interpreter
        # Note: Using 127.0.0.1 instead of localhost is important for LLDB compatibility
        logger.debug(f"Connecting to 127.0.0.1:{self.port}")

        interpreter = self.debugger.GetCommandInterpreter()
        result = lldb.SBCommandReturnObject()
        connect_cmd = f"gdb-remote 127.0.0.1:{self.port}"

        logger.debug(f"Executing: {connect_cmd}")
        interpreter.HandleCommand(connect_cmd, result)

        error = lldb.SBError()
        if not result.Succeeded():
            error_msg = result.GetError() if result.GetError() else "Unknown error"
            logger.error(f"Failed to connect: {error_msg}")
            self._cleanup()
            raise RuntimeError(f"Failed to connect to rr replay: {error_msg}")

        # Get the process from the target
        self.process = self.target.GetProcess()

        if not self.process or not self.process.IsValid():
            logger.error("Failed to get valid process after connection")
            self._cleanup()
            raise RuntimeError("Failed to get valid process after connection")

        # Verify connection and get initial state
        state = self.process.GetState()
        logger.info(f"Connected to rr replay. Process state: {lldb.SBDebugger.StateAsCString(state)}")

        if self.process.IsValid():
            logger.info(f"Process ID: {self.process.GetProcessID()}")

        # Log loaded modules to verify symbols are loaded
        num_modules = self.target.GetNumModules()
        logger.info(f"Loaded {num_modules} modules")
        if num_modules > 0:
            main_module = self.target.GetModuleAtIndex(0)
            if main_module and main_module.IsValid():
                logger.info(f"Main module: {main_module.GetFileSpec().GetFilename()}")
                logger.debug(f"Module path: {main_module.GetFileSpec().GetDirectory()}/{main_module.GetFileSpec().GetFilename()}")

                # Check if symbols are available
                num_symbols = main_module.GetNumSymbols()
                logger.debug(f"Main module has {num_symbols} symbols")

    def run_cmd(self, cmd: str) -> str:
        """
        Execute a command in the LLDB session and return the output.

        In synchronous mode (SetAsync(False)), commands automatically block
        until completion, so no additional waiting is needed.

        Args:
            cmd: The LLDB command to execute (can be standard debugger commands)

        Returns:
            str: The output from the command, truncated if too long
        """
        if not self.debugger or not self.debugger.IsValid():
            raise RuntimeError("LLDB debugger is not initialized")

        logger.info(f"Running LLDB command: {cmd}")

        # Create a command return object to capture results
        result = lldb.SBCommandReturnObject()
        interpreter = self.debugger.GetCommandInterpreter()

        # Handle the command (blocks until completion in sync mode)
        return_status = interpreter.HandleCommand(cmd, result)

        # Collect output
        output_parts = []

        if result.GetOutput():
            output_parts.append(result.GetOutput())

        if result.GetError():
            output_parts.append(result.GetError())

        output = ''.join(output_parts)

        # Log command status
        success = result.Succeeded()
        logger.debug(f"Command '{cmd}' - Succeeded: {success}, Return status: {return_status}")
        logger.debug(f"Output ({len(output)} bytes):\n{output[:500]}")  # Log first 500 chars

        # For execution commands, log stop reason
        cmd_stripped = cmd.strip().lower()
        execution_cmds = ['c', 'continue', 's', 'step', 'n', 'next', 'finish', 'si', 'ni', 'stepi', 'nexti']

        if any(cmd_stripped == ec or cmd_stripped.startswith(ec + ' ') for ec in execution_cmds):
            if self.process and self.process.IsValid():
                state = self.process.GetState()
                state_str = lldb.SBDebugger.StateAsCString(state)
                logger.debug(f"After '{cmd}', process state: {state_str}")

                # If stopped, add stop reason info
                if state == lldb.eStateStopped:
                    thread = self.process.GetSelectedThread()
                    if thread and thread.IsValid():
                        stop_reason = thread.GetStopReason()
                        stop_desc = thread.GetStopDescription(256)
                        logger.info(f"Stop reason: {stop_reason}, Description: {stop_desc}")

        # Truncate if too long (matching RRController behavior)
        max_len = 1024 * 6
        if len(output) > max_len:
            output = output[:max_len] + '...'

        return output

    # Alias for compatibility with RRController interface
    # In LLDB sync mode, run_cmd already waits for completion
    def run_cmd_and_wait_stop(self, cmd: str) -> str:
        """Alias for run_cmd() - maintained for RRController interface compatibility."""
        return self.run_cmd(cmd)

    def _cleanup(self):
        """Clean up rr process."""
        logger.debug("Cleaning up rr process...")
        try:
            if self.rr_process and self.rr_process.poll() is None:
                logger.debug("Terminating rr process...")
                self.rr_process.terminate()
                try:
                    self.rr_process.wait(timeout=5)
                    logger.debug("rr process terminated successfully")
                except subprocess.TimeoutExpired:
                    logger.warning("rr process did not terminate, killing...")
                    self.rr_process.kill()
                    self.rr_process.wait()
                    logger.debug("rr process killed")
        except Exception as e:
            logger.error(f"Error cleaning up rr process: {e}")

    def exit(self):
        """Exit the LLDB session and clean up."""
        logger.info("Exiting LLDB session")

        try:
            # Kill the process if running
            if self.process and self.process.IsValid():
                logger.debug("Killing debugged process...")
                error = self.process.Kill()
                if error.Fail():
                    logger.warning(f"Failed to kill process: {error.GetCString()}")

            # Detach from target
            if self.target and self.target.IsValid():
                logger.debug("Deleting target...")
                self.debugger.DeleteTarget(self.target)
                self.target = None

            # Clean up rr process
            self._cleanup()

            # Destroy the debugger
            if self.debugger and self.debugger.IsValid():
                logger.debug("Destroying LLDB debugger...")
                lldb.SBDebugger.Destroy(self.debugger)
                self.debugger = None

        except Exception as e:
            logger.error(f"Error during exit: {e}")
        finally:
            logger.debug("Terminating LLDB...")
            lldb.SBDebugger.Terminate()
            logger.info("LLDB session closed")


if __name__ == "__main__":
    # Configure logging
    logger.remove()  # Remove default handler
    logger.add(
        "server.log",
        level="DEBUG",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {file}:{line} | {message}"
    )
    logger.add(
        sys.stderr,
        level='INFO',
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {message}"
    )

    # Get trace directory
    trace_dir = None
    if len(sys.argv) >= 2:
        trace_dir = sys.argv[1]
    else:
        trace_dir = os.path.join(os.environ['HOME'], '.local', 'share', 'rr', 'latest-trace')

    if not os.path.exists(trace_dir):
        logger.error(f"Trace directory does not exist: {trace_dir}")
        sys.exit(1)

    logger.info(f"Using trace directory: {trace_dir}")

    try:
        # Initialize controller
        controller = LLDBRRController(trace_dir)

        # Test some basic commands
        logger.info("=" * 60)
        logger.info("Testing continue command...")
        logger.info("=" * 60)
        rets = controller.run_cmd("c")
        logger.info(f"Continue result:\n{rets}")

        logger.info("=" * 60)
        logger.info("Testing backtrace command...")
        logger.info("=" * 60)
        rets = controller.run_cmd('bt')
        logger.info(f"Backtrace result:\n{rets}")

        logger.info("=" * 60)
        logger.info("Testing frame up command...")
        logger.info("=" * 60)
        rets = controller.run_cmd('up')
        logger.info(f"Up result:\n{rets}")

        # Exit
        controller.exit()
        logger.info("Test completed successfully!")

    except Exception as e:
        logger.exception(f"Test failed with error: {e}")
        sys.exit(1)
