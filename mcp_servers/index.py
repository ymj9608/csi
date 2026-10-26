import hashlib,json,time,uuid
from pathlib import Path
from qdrant_client import models
from .vector import client,embed,COLLECTION,DIM
ROOT=Path(__file__).resolve().parents[1]
def index():
    catalog=json.loads((ROOT/'rag/catalog.json').read_text(encoding='utf-8'));db=client()
    for attempt in range(20):
        try:
            if not db.collection_exists(COLLECTION):db.create_collection(COLLECTION,vectors_config=models.VectorParams(size=DIM,distance=models.Distance.COSINE))
            break
        except Exception:
            if attempt==19:raise
            time.sleep(1)
    vectors=embed([p['sectionTitle']+' '+p['content'] for p in catalog])
    db.upsert(COLLECTION,points=[models.PointStruct(id=str(uuid.UUID(hashlib.md5(p['chunkId'].encode()).hexdigest())),vector=v,payload=p) for p,v in zip(catalog,vectors)],wait=True)
    db.delete(COLLECTION,points_selector=models.FilterSelector(filter=models.Filter(must_not=[models.FieldCondition(key='chunkId',match=models.MatchAny(any=[p['chunkId'] for p in catalog]))])),wait=True)
    count=db.count(COLLECTION,exact=True).count
    assert count==len(catalog)
    print(json.dumps({'indexedChunks':count,'documents':len({p['documentId'] for p in catalog}),'embedding':'local-hashing-char-2-4-1024','vectorStore':'Qdrant'}))
if __name__=='__main__':index()
