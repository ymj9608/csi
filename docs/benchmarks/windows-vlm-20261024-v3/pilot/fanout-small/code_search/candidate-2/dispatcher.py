from broker import publish
from state import MESSAGES

def publish_event(event, fail=False):
    # Determine channels based on deployment.json and fail flag
    with open('deployment.json') as f:
        deployment = json.load(f)
    
    # Internal channel is always r1
    channels = ['r1']
    
    # External channels based on fail flag
    if fail:
        channels.extend([k for k, v in deployment.items() if v['boundary'] == 'EXTERNAL'])
    else:
        channels.extend([k for k, v in deployment.items() if v['boundary'] == 'INTERNAL'])
    
    # Publish to each channel
    for channel in channels:
        publish(channel, event)
