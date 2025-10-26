import os
import sys
from typing import Optional, List, Dict, Tuple
import logging, json, time
from pygdbmi.IoManager import logger
from pygdbmi.gdbcontroller import GdbController

logging.basicConfig(
    filename='server.log',
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s',
    filemode='w')

class RRController(GdbController):
    NOTIFY = 'notify'
    STOPPED = 'stopped'

    def __init__(self, trace_dir: str, time_to_check_for_additional_output_sec:float=1):
        self.trace_dir = trace_dir
        command = ['rr', 'replay', '-i=mi', '--debugger-option="--interpreter=mi3"',  trace_dir]
        super().__init__(command=command, time_to_check_for_additional_output_sec=time_to_check_for_additional_output_sec)
        self.logger = logging.getLogger('rr_controller')
        self._wait([(RRController.NOTIFY, RRController.STOPPED)])
        self.status = None

    def _check_wait_result(self, resps:List[Dict], targets:List[Tuple[str, str]]) -> List[Dict]:
        for resp in resps:
            resp_typ = (resp['type'], resp['message'])
            self.logger.debug(f'checking {resp_typ} against {targets}')
            if resp_typ in targets:
                return True
        return False

    def _wait(self, targets:List[Tuple[str, str]]) -> List[Dict]:
        resps = []
        while True:
            responses = self.get_gdb_response(timeout_sec=0.5, raise_error_on_timeout=False)
            if responses:
                self.logger.info(f'responses: {json.dumps(responses, indent=2)}')
                resps.extend(responses)
            else:
                continue

            if self._check_wait_result(responses, targets):
                break

        return resps

    def run_cmd(self, cmd:str) -> List[Dict]:
        resps = self.write(cmd)
        self.logger.info(f'running cmd: {cmd}')
        self.logger.info(f'responses: {json.dumps(resps, indent=2)}')
        return resps

    def _run_cmd_and_wait(self, cmd:str, targets:List[Tuple[str, str]]) -> List[Dict]:
        resps = self.run_cmd(cmd)
        if self._check_wait_result(resps, targets):
            return resps
        return self._wait(targets)

    def run_cmd_and_wait_stop(self, cmd:str):
        # TODO: might stop at other things, we should check for that later
        targets = [(RRController.NOTIFY, RRController.STOPPED)]
        self._run_cmd_and_wait(cmd, targets)

    def exit(self):
        return self._run_cmd_and_wait('exit', [('notify', 'thread-group-exited')])

if __name__ == "__main__":
    trace_dir = None
    if len(sys.argv) >= 2:
        trace_dir = sys.argv[1]
    else:
        trace_dir = os.path.join(os.environ['HOME'], '.local', 'share', 'rr', 'latest-trace')
    controller = RRController(trace_dir)
    controller.run_cmd_and_wait_stop("c")
    controller.exit()
