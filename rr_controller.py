import os
import sys
from typing import Optional, List, Dict, Tuple
import json, time
from pygdbmi.gdbcontroller import GdbController
from loguru import logger

class MessageType:
    NOTIFY = 'notify'
    RESULT = 'result'

class Message:
    DONE = 'done'
    STOPPED = 'stopped'
    ERROR = 'error'

class RRController(GdbController):
    def __init__(self, trace_dir: str, time_to_check_for_additional_output_sec:float=1):
        self.trace_dir = trace_dir
        command = ['rr', 'replay', '-i=mi', '--debugger-option="--interpreter=mi3"',  trace_dir]
        super().__init__(command=command, time_to_check_for_additional_output_sec=time_to_check_for_additional_output_sec)
        self._wait([(MessageType.NOTIFY, Message.STOPPED)])
        self.status = None

    def _check_wait_result(self, resps:List[Dict], targets:List[Tuple[str, str]]) -> List[Dict]:
        for resp in resps:
            resp_typ = (resp['type'], resp['message'])
            if resp_typ in targets:
                logger.debug(f'target {resp_typ} found, return now.')
                return True
        return False

    def _wait(self, targets:List[Tuple[str, str]]) -> List[Dict]:
        resps = []
        while True:
            responses = self.get_gdb_response(timeout_sec=0.5, raise_error_on_timeout=False)
            if responses:
                logger.debug(f'responses: {json.dumps(responses, indent=2)}')
                resps.extend(responses)
            else:
                continue

            if self._check_wait_result(responses, targets):
                break

        return resps

    def run_cmd(self, cmd:str) -> List[Dict]:
        resps = self.write(cmd, timeout_sec=8848)
        logger.info(f'running cmd: {cmd}')
        logger.debug(f'responses: {json.dumps(resps, indent=2)}')
        return resps

    def _run_cmd_and_wait(self, cmd:str, targets:List[Tuple[str, str]]) -> List[Dict]:
        resps = self.run_cmd(cmd)
        if self._check_wait_result(resps, targets):
            return resps
        return resps + self._wait(targets)

    def run_cmd_and_wait_stop(self, cmd:str) -> str:
        # TODO: might stop at other things, we should check for that later
        targets = [
            (MessageType.NOTIFY, Message.STOPPED),
            (MessageType.RESULT, Message.DONE),
            (MessageType.RESULT, Message.ERROR),
        ]
        oresps = self._run_cmd_and_wait(cmd, targets)
        resps = [resp for resp in oresps if resp['type'] != 'notify' and resp['payload'] is not None]
        strs = ''.join([resp['payload'] for resp in resps])
        max_len = 1024 * 6
        if len(strs) > max_len:
            strs = strs[:max_len] + '...'

        return strs

    def exit(self):
        return self._run_cmd_and_wait('exit', [('notify', 'thread-group-exited')])

if __name__ == "__main__":
    logger.remove()  # Remove default handler
    logger.add("server.log", level="DEBUG", format="{time:YYYY-MM-DD HH:mm:ss} {level} {file}:{line} {message}")
    logger.add(sys.stderr, level='INFO', format="{time:YYYY-MM-DD HH:mm:ss} {level} {file}:{line} {message}")
    trace_dir = None
    if len(sys.argv) >= 2:
        trace_dir = sys.argv[1]
    else:
        trace_dir = os.path.join(os.environ['HOME'], '.local', 'share', 'rr', 'latest-trace')
    controller = RRController(trace_dir)
    rets = controller.run_cmd_and_wait_stop("c")
    logger.info(rets)
    rets = controller.run_cmd_and_wait_stop('bt')
    logger.info(rets)
    rets = controller.run_cmd_and_wait_stop('up')
    logger.info(rets)
    controller.exit()
