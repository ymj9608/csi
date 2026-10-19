"""Test actual SSE updates and duplicate Kafka event consumption."""
import asyncio,json,uuid,os
import httpx
from aiokafka import AIOKafkaProducer
from demo import env,login
async def main():
    env();c=login('http://127.0.0.1:8080');scan=next(s for s in c.get('/api/scans').json() if s['findingCount']>0);f=c.get('/api/scans/'+scan['id']+'/findings').json()[0]
    async with httpx.AsyncClient(base_url='http://127.0.0.1:8080',cookies=c.cookies,timeout=10) as client:
        async with client.stream('GET','/api/scans/'+scan['id']+'/stream') as response:
            assert response.status_code==200
            lines=response.aiter_lines();first=False
            async for line in lines:
                if line.startswith('data:'):
                    if not first:
                        first=True;c.post('/api/findings/'+f['id']+'/review',json={'status':'REVIEWING'}).raise_for_status()
                    else:
                        assert scan['id'] in line;break
    event={'eventId':str(uuid.uuid4()),'scanId':scan['id'],'projectId':scan['projectId'],'repository':scan['repository'],'commitSha':scan['commitSha'],'correlationId':scan['id'],'timestamp':'2026-10-19T00:00:00Z','eventType':'SCAN_LOG','node':'validate_scan'}
    producer=AIOKafkaProducer(bootstrap_servers='127.0.0.1:9092');await producer.start()
    before=len(c.get('/api/scans/'+scan['id']+'/logs').json())
    try:
        for _ in range(2):await producer.send_and_wait('scan.log',json.dumps(event).encode(),key=scan['id'].encode())
        for _ in range(30):
            after=len(c.get('/api/scans/'+scan['id']+'/logs').json())
            if after>before:break
            await asyncio.sleep(.5)
        await asyncio.sleep(1)
        assert len(c.get('/api/scans/'+scan['id']+'/logs').json())==before+1
    finally:await producer.stop()
    print(json.dumps({'sseLiveUpdate':'PASS','duplicateKafkaEvent':'PASS'}))
if __name__=='__main__':asyncio.run(main())
