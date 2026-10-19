"""Extract supplied PDFs into page/section chunks; never invent clause locations."""
from pathlib import Path
import hashlib, json, re
from pypdf import PdfReader
BASE=Path(__file__).resolve().parents[1]
def prepare():
    chunks=[]
    for path in sorted((BASE/'rag/documents').glob('*.pdf')):
        internal='사내' in path.name
        document_id='PG-POL-2026-01' if internal else 'PG-REF-2026-01'
        for page_no,page in enumerate(PdfReader(path).pages,1):
            text=page.extract_text() or ''
            starts=list(re.finditer(r'(?m)^(POL-\d{2}|REF-\d{2})\s+([^\n]+)',text))
            if not starts: continue
            for i,m in enumerate(starts):
                content=text[m.start():starts[i+1].start() if i+1<len(starts) else len(text)].strip()
                chunks.append(dict(chunkId=hashlib.sha256(f'{document_id}:{page_no}:{m.group(1)}:{m.start()}'.encode()).hexdigest()[:24],documentId=document_id,documentType='INTERNAL_POLICY' if internal else 'EXTERNAL_REFERENCE',documentVersion='1.0',sectionId=m.group(1),sectionTitle=m.group(2).strip(),pageNumber=page_no,source=path.name,content=content))
    all_internal='\n'.join(p.extract_text() or '' for f in (BASE/'rag/documents').glob('*사내*.pdf') for p in PdfReader(f).pages)
    assert re.search(r'Work Factor는 최소 12',all_internal), 'Policy source changed: revalidate bcrypt control'
    policy={'version':'PG-POL-2026-01@1.0','documentId':'PG-POL-2026-01','bcryptMinCost':12,'approvedFields':['account_id','accountId','email','password_hash','passwordHash'],'transientOnlyFields':['password','rawPassword'],'restrictedFields':['phoneNumber','residentRegistrationNo'],'authOnlyFields':['accessToken','refreshToken'],'sourceSection':'POL-04.1','sourcePage':4,'inventorySection':'POL-02','inventoryPage':3,'fictionalTrainingPolicy':True}
    (BASE/'rag/catalog.json').write_text(json.dumps(chunks,ensure_ascii=False,indent=2))
    (BASE/'rag/policy.json').write_text(json.dumps(policy,ensure_ascii=False,indent=2))
    print(f'Extracted {len(chunks)} chunks from 2 supplied PDFs; vector indexing is a separate step.')
if __name__=='__main__': prepare()
