"""Controlled Kafka outage check; always unpauses the CSI broker on exit."""
import subprocess,time,json,os
from demo import env,run,login

def main():
    env();c=login('http://127.0.0.1:8080')
    subprocess.run(['docker','compose','pause','kafka'],check=True,capture_output=True)
    try:
        sid=run('fixed',wait=False)
        for _ in range(100):
            s=c.get('/api/scans/'+sid).json()
            if s['status']=='FAILED':break
            assert s['status']!='COMPLETED','Kafka outage reported as success'
            time.sleep(1)
        else:raise AssertionError('Bounded Kafka retries did not mark scan failed')
        logs=c.get('/api/scans/'+sid+'/logs').json()
        attempts=[x for x in logs if x['eventType']=='KAFKA_RETRY']
        assert len(attempts)==3
        print(json.dumps({'scanId':sid,'status':s['status'],'kafkaAttempts':len(attempts),'outageTest':'PASS'}))
    finally:subprocess.run(['docker','compose','unpause','kafka'],check=True,capture_output=True)
if __name__=='__main__':main()
