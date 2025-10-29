import json
from loguru import logger


with open('gg.json', 'r') as f:
    oresps = json.load(f)

cmd = 'bt'
# resps = [resp for resp in oresps if resp['type'] != 'notify' and hasattr(resp, 'payload')]
resps = [resp for resp in oresps if resp['type'] != 'notify' and resp['payload'] is not None]
logger.info(f'resps: {json.dumps(resps, indent=2)}')

strs = ''.join([resp['payload'] for resp in resps])
# logger.info(f'run_cmd: {cmd} -> {strs}, original resps: {json.dumps(oresps, indent=2)}')
logger.info(f'strs: {strs}')


# for resp in data:
#     if resp['type'] == 'notify' or not hasattr(resp, 'payload'):
#         continue
#     print(resp['payload'])