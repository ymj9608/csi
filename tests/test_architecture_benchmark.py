from scripts.benchmark_architecture import batches, select_sources, score


def test_batching_preserves_every_numbered_line_and_budget():
    files = {'a.py':'x = 1\n'*20, 'b.py':'y = 2\n'*90, 'c.py':'z = 3\n'*7}
    observed = {name:[] for name in files}
    for batch in batches(files, limit=100):
        assert sum(len(s['source'].encode()) for s in batch.values()) <= 100
        for segment in batch.values():
            observed[segment['filePath']].extend(segment['source'].splitlines())
    for name, text in files.items():
        assert observed[name] == [f'{n}|{line}' for n,line in enumerate(text.splitlines(),1)]


def test_selection_never_opens_paths_from_model_and_adds_direct_dependency():
    files={'backend/app/api.py':'from app.core import auth\nimport app.passwords\n',
           'backend/app/passwords.py':'hash_password = None\n', 'backend/jobs/export.py':'data = None\n'}
    selected,unmatched=select_sources(files,{'codeHints':['backend/app/api.py','../../.env','/etc/passwd']})
    assert set(selected)=={'backend/app/api.py','backend/app/passwords.py'}
    assert unmatched==['../../.env','/etc/passwd']


def test_quality_requires_source_backed_location_and_includes_omitted_truth():
    truth={'positives':[{'id':'v1','category':'weak_password_hash','path':'a.py','line_start':3,'line_end':5},
                        {'id':'v2','category':'plaintext_pii_export','path':'hidden.py','line_start':1,'line_end':8}]}
    found=[{'filePath':'a.py','category':'weak_password_hash','line':4,'evidenceValid':True}]
    assert score(found,truth)['recall']==.5
    assert score(found,truth)['missedIds']==['v2']
    found[0]['evidenceValid']=False
    assert score(found,truth)['tp']==0
    assert score(found,truth)['fp']==1


def test_single_long_unicode_line_is_fragmented_without_loss():
    line='긴 소스 줄🙂'*100
    chunks=batches({'view.vue':line+'\n'},limit=100)
    fragments=[]
    for batch in chunks:
        assert sum(len(s['source'].encode()) for s in batch.values())<=100
        for segment in batch.values():
            fragments.extend(row.split('|',1)[1] for row in segment['source'].splitlines())
    assert ''.join(fragments)==line
