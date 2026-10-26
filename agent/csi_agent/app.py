import asyncio,json,os,uuid
from contextlib import asynccontextmanager
from datetime import datetime,timezone
import httpx
from aiokafka import AIOKafkaConsumer,AIOKafkaProducer
from fastapi import FastAPI
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.types import Command
from psycopg.conninfo import make_conninfo
from .graph import build_graph
runtime={'ready':False}
async def work():
    bootstrap=os.environ.get('KAFKA_BOOTSTRAP_SERVERS','127.0.0.1:9092')
    producer=AIOKafkaProducer(bootstrap_servers=bootstrap,enable_idempotence=True,request_timeout_ms=15000,value_serializer=lambda v:json.dumps(v,ensure_ascii=False).encode())
    consumer=AIOKafkaConsumer('scan.request',bootstrap_servers=bootstrap,group_id='csi-agent-v1',auto_offset_reset='earliest',enable_auto_commit=False,max_poll_records=1,max_poll_interval_ms=2100000)
    async def emit(topic,event,kind,**data):
        payload={k:event[k] for k in ('scanId','projectId','repository','commitSha','correlationId')}
        payload.update(eventId=str(uuid.uuid4()),eventType=kind,timestamp=datetime.now(timezone.utc).isoformat(),**data)
        await asyncio.wait_for(producer.send_and_wait(topic,payload,key=event['scanId'].encode()),20)
    for attempt in range(20):
        try:await producer.start();await consumer.start();break
        except Exception:
            if attempt==19:raise
            await asyncio.sleep(2)
    conn=make_conninfo(host=os.environ.get('DATABASE_HOST','127.0.0.1'),port='5432',dbname='csi',user='csi',password=os.environ['DATABASE_PASSWORD'])
    async with AsyncPostgresSaver.from_conn_string(conn) as saver:
        await saver.setup();graph=build_graph(saver,emit);runtime['ready']=True
        try:
            async for record in consumer:
                event=json.loads(record.value);config={'configurable':{'thread_id':event['scanId']},'recursion_limit':60}
                deadline=asyncio.get_running_loop().time()+1800
                for attempt in range(2):
                    try:
                        snapshot=await graph.aget_state(config)
                        if event['eventType']=='APPROVAL_DECIDED':
                            if not snapshot.next:break
                            async with httpx.AsyncClient(timeout=10) as client:
                                response=await client.get(os.environ.get('CSI_BACKEND_URL','http://127.0.0.1:8080')+'/internal/scans/'+event['scanId']+'/approval',headers={'Authorization':'Bearer '+os.environ['CSI_INTERNAL_TOKEN']});response.raise_for_status();approval=response.json()
                            if approval['status'] not in {'APPROVED','REJECTED','EXECUTED'}:raise ValueError('Approval not finalized')
                            action=Command(resume={'approvalId':approval['id'],'status':'APPROVED' if approval['status']=='EXECUTED' else approval['status']})
                        else:
                            if snapshot.values and not snapshot.next:break
                            action=None if snapshot.values else {'event':event}
                        async with asyncio.timeout_at(deadline):await graph.ainvoke(action,config)
                        break
                    except Exception:
                        await emit('scan.log',event,'SCAN_LOG',node='retry' if attempt==0 else 'failed')
                        if attempt==0:await asyncio.sleep(1)
                        else:
                            await emit('scan.dlq',event,'SCAN_DEAD_LETTER',reason='ANALYSIS_FAILED',attempts=2)
                            if event['eventType']!='APPROVAL_DECIDED':await emit('scan.result',event,'SCAN_RESULT',status='FAILED',analysisMode='FAILED',findings=[])
                await consumer.commit()
        finally:runtime['ready']=False;await consumer.stop();await producer.stop()
@asynccontextmanager
async def lifespan(app):
    task=asyncio.create_task(work());runtime['task']=task
    yield
    task.cancel()
    try:await task
    except asyncio.CancelledError:pass
app=FastAPI(title='CSI Agent',lifespan=lifespan)
@app.get('/health')
def health():return {'ready':runtime['ready'],'workerAlive':not runtime['task'].done()}
