"""Local deterministic lexical embeddings. No remote model or secret transmission."""
import os
from sklearn.feature_extraction.text import HashingVectorizer
from qdrant_client import QdrantClient,models
COLLECTION='csi-guidelines-v1'
DIM=1024
vectorizer=HashingVectorizer(n_features=DIM,analyzer='char',ngram_range=(2,4),alternate_sign=False,norm='l2')
def embed(texts):return vectorizer.transform(texts).toarray().tolist()
def client():return QdrantClient(url=os.environ.get('QDRANT_URL','http://127.0.0.1:6333'),timeout=10,check_compatibility=False)
RULE_SECTIONS={'SEC-01':(['POL-04'],['REF-04']),'SEC-02':(['POL-04'],['REF-04','REF-05']),'SEC-03':(['POL-04'],['REF-05']),'SEC-04':(['POL-04'],['REF-04']),'SEC-05':(['POL-05'],['REF-06']),'POL-01':(['POL-02','POL-03'],['REF-01'])}
def search(rule_id,internal,query):
    if rule_id not in RULE_SECTIONS:raise ValueError('Unsupported rule')
    sections=RULE_SECTIONS[rule_id][0 if internal else 1]
    result=client().query_points(collection_name=COLLECTION,query=embed([query])[0],query_filter=models.Filter(must=[models.FieldCondition(key='documentType',match=models.MatchValue(value='INTERNAL_POLICY' if internal else 'EXTERNAL_REFERENCE')),models.FieldCondition(key='sectionId',match=models.MatchAny(any=sections))]),limit=3,with_payload=True)
    return [p.payload for p in result.points]
