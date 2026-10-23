#!/usr/bin/env python3
"""Summarize a finished Qwen drawing experiment without invoking any model."""
from __future__ import annotations

import json
from pathlib import Path
import statistics
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.benchmark_readable_architecture import PUBLIC, VISION_ORDER, REVIEW_ORDER, structured_context
from scripts.benchmark_architecture import digest


def diagnostic(raw,graph):
    """Literal post-run diagnostics, including invalid graphs; never retrieval input."""
    message=raw.get('message',{})
    value=message.get('content') or message.get('thinking')
    try:
        data=json.loads(value)
        components=data['components']; flows=data['flows']
        if not isinstance(components,list) or not isinstance(flows,list):
            return None
        ids={c['id'] for c in components if isinstance(c,dict) and isinstance(c.get('id'),str)}
        pairs={(f['from'],f['to']) for f in flows if isinstance(f,dict) and isinstance(f.get('from'),str) and isinstance(f.get('to'),str)}
        known={c['id'] for c in graph['nodes']}; expected={(f['from'],f['to']) for f in graph['edges']}
        return {'literalComponentIdsMatched':len(ids & known),'literalDirectedEndpointsMatched':len(pairs & expected),
                'undeclaredEndpointIds':sorted({x for pair in pairs for x in pair}-ids),
                'modeMisclassifiedAsProtection':sum(f.get('protection','').strip().upper() in {'SYNC','ASYNC','SYNCHRONOUS','ASYNCHRONOUS'} for f in flows if isinstance(f,dict) and isinstance(f.get('protection'),str)),
                'scope':'Post-run literal comparison against graph IDs, even for schema-invalid output; not an accepted or repaired context.'}
    except (ValueError,TypeError,KeyError):
        return None


def load_report(directory=PUBLIC):
    directory=Path(directory)
    protocol_raw=(directory/'protocol.json').read_bytes()
    protocol=json.loads(protocol_raw)
    log_raw=(directory/'measurements.jsonl').read_bytes()
    rows=[json.loads(line) for line in log_raw.decode().splitlines() if line.strip()]
    if not rows or rows[-1].get('event')!='finished' or sum(r['event']=='finished' for r in rows)!=1:
        raise ValueError('EXPERIMENT_NOT_FINISHED')
    metadata=[r for r in rows if r['event']=='metadata']
    if len(metadata)!=1 or metadata[0]['protocolSha256']!=digest(protocol_raw):
        raise ValueError('PROTOCOL_METADATA_MISMATCH')
    for path,sha in protocol['hashes'].items():
        if digest((ROOT/path).read_bytes())!=sha:
            raise ValueError('FROZEN_INPUT_CHANGED: '+path)
    expected=rows[-1]['rawHashes']
    raw_dir=directory/'raw'
    if set(expected)!={p.name for p in raw_dir.glob('*.json')}:
        raise ValueError('RAW_RESPONSE_SET_MISMATCH')
    for name,sha in expected.items():
        if digest((raw_dir/name).read_bytes())!=sha:
            raise ValueError('RAW_RESPONSE_CHANGED: '+name)
    calls={r['sequence']:r for r in rows if r['event']=='vision_call'}
    graph=json.loads((ROOT/'tests/fixtures/complex_architecture/graph.json').read_text())
    vision_results=[r for r in rows if r['event']=='vision_result']
    if [(r['sequence'],r['variant']) for r in vision_results]!=list(enumerate(VISION_ORDER,1)):
        raise ValueError('VISION_ORDER_MISMATCH')
    vision={}
    for variant in ('original','readable'):
        runs=[]
        for row in vision_results:
            if row['variant']!=variant:
                continue
            metrics=calls.get(row['sequence'],{}).get('metrics')
            raw_path=raw_dir/f'vision-{row["sequence"]}-{variant}.json'
            raw_diagnostic=diagnostic(json.loads(raw_path.read_text()),graph) if raw_path.exists() else None
            runs.append({**row,'metrics':metrics,'rawDiagnostic':raw_diagnostic})
        valid=[r for r in runs if r['complete']]
        vision[variant]={'runs':runs,'validRuns':len(valid),'expectedRuns':2,
            'meanMatchedComponents':statistics.mean(r['quality']['componentIdentitiesMatched'] for r in valid) if valid else None,
            'meanMatchedEdges':statistics.mean(r['quality']['edgesMatched'] for r in valid) if valid else None,
            'meanInputTokens':statistics.mean(r['metrics']['prompt_eval_count'] for r in runs) if all(r['metrics'] for r in runs) else None,
            'meanOutputTokens':statistics.mean(r['metrics']['eval_count'] for r in runs) if all(r['metrics'] for r in runs) else None,
            'meanWallMs':statistics.mean(r['phaseWallMs'] for r in runs),
            'firstValidSequence':valid[0]['sequence'] if valid else None}
    trials=[r for r in rows if r['event']=='trial']
    if [r['arm'] for r in trials]!=list(REVIEW_ORDER):
        raise ValueError('REVIEW_ORDER_MISMATCH')
    reviews={}
    truth=json.loads((ROOT/'tests/fixtures/complex_architecture/ground_truth.json').read_text())
    manifest=json.loads((ROOT/'tests/fixtures/complex_architecture/manifest.json').read_text())
    service_ids={entry['path'].split('/')[1] for entry in manifest['files'] if entry['path'].startswith('services/')}
    required={r['path'] for r in truth['required_context_paths']}
    for trial in trials:
        name=trial['arm']; selected=trial.get('initialPaths',[])
        calls_=trial.get('calls',[])
        audit=trial.get('responseAudit',{})
        if name in vision and trial.get('chosenVisionSequence')!=vision[name]['firstValidSequence']:
            raise ValueError('CONTEXT_NOT_FIRST_VALID')
        sequence=trial.get('chosenVisionSequence')
        if sequence is not None:
            context_file=directory/f'context-{sequence}-{name}.json'
            raw=json.loads((raw_dir/f'vision-{sequence}-{name}.json').read_text())
            if json.loads(context_file.read_text())!=structured_context(raw)[0]:
                raise ValueError('CONTEXT_CHANGED_AFTER_EXTRACTION')
        plan=trial['plan']
        if json.loads((directory/f'{name}-plan.json').read_text())!=plan:
            raise ValueError('PLAN_CHANGED')
        quality=trial.get('quality')
        raw_complete=bool(trial.get('complete'))
        reviews[name]={'complete':raw_complete,'initialFiles':len(selected),
            'effectiveFiles':len(trial.get('effectivePaths',[])),
            'initialRequiredSelected':len(required & set(selected)),
            'totals':trial.get('totals'),'endToEndWallMs':trial.get('endToEndWallMs'),
            'quality':quality,'responseAudit':audit,'decision':plan['decision'],'mappingCount':plan['mappingCount'],
            'missingContextReasons':[item for item in plan.get('omittedCandidates',[])
                                     if quality and item['path'] in quality['missingRequiredContext']],
            'chosenVisionSequence':sequence,'visionAvailable':trial.get('visionAvailable'),
            'unmappedExactServiceIds':[m['componentId'] for m in plan['mapping']
                                      if m['componentId'] in service_ids and m['status']!='MATCHED'],
            'unresolvedNeeds':trial.get('unresolvedNeeds',[]),'rejectedNeeds':trial.get('rejectedNeeds',[]),
            'errors':trial.get('errors',[]),'error':trial.get('error'),
            'initialRequestHashes':[c['requestSha256'] for c in calls_ if not c['followup']],
            'allRequestHashes':[c['requestSha256'] for c in calls_]}
        if quality:
            reviews[name]['allMeasuredChecksPass']=bool(raw_complete and len(quality['verifiedMatches'])==quality['expected']
                and not quality['missingRequiredContext'] and not quality['negativeControlFlags']
                and not quality['extraCandidates'] and not quality['invalidEvidence']
                and not audit.get('invalidSupportEvidence') and not audit.get('followupResponseNeeds')
                and not trial.get('unresolvedNeeds') and not trial.get('rejectedNeeds'))
        else:
            reviews[name]['allMeasuredChecksPass']=False
        reviews[name]['firstUse']=None
        reviews[name]['failedFirstAttemptCombined']=None
        if sequence is not None and reviews[name]['totals']:
            first=next(r for r in vision[name]['runs'] if r['sequence']==sequence)
            reviews[name]['firstUse']={
                'wallMs':first['phaseWallMs']+trial['endToEndWallMs'],
                'inputTokens':first['metrics']['prompt_eval_count']+trial['totals']['prompt_eval_count'],
                'outputTokens':first['metrics']['eval_count']+trial['totals']['eval_count'],
                'scope':'Sum of first valid image extraction/validation/persistence and downstream planning/review. Not one integrated API request.'}
        elif name in vision and reviews[name]['totals']:
            first=vision[name]['runs'][0]
            reviews[name]['failedFirstAttemptCombined']={
                'wallMs':first['phaseWallMs']+trial['endToEndWallMs'],
                'inputTokens':None if first['metrics'] is None else first['metrics']['prompt_eval_count']+trial['totals']['prompt_eval_count'],
                'scope':'First failed image attempt plus fallback review cost, not successful architecture-assisted latency.'}
    comparisons=[]
    for a,b in [('code_index','original'),('code_index','readable'),('original','readable'),('readable','oracle')]:
        x,y=reviews[a],reviews[b]
        comparisons.append({'left':a,'right':b,
            'sameInitialRequests':bool(x['initialRequestHashes']) and x['initialRequestHashes']==y['initialRequestHashes'],
            'sameAllRequests':bool(x['allRequestHashes']) and x['allRequestHashes']==y['allRequestHashes']})
    return {'schemaVersion':1,'metadata':metadata[0],'protocolSha256':digest(protocol_raw),
            'logSha256':digest(log_raw),'visionModel':protocol['visionModel'],'reviewModel':protocol['reviewModel'],
            'vision':vision,'reviews':reviews,'comparisons':comparisons,'protocolLimits':protocol['limits']}


def number(value):
    return '미측정' if value is None else f'{value:,.1f}'


def sec(value):
    return '미측정' if value is None else f'{value/1000:,.2f}'


def render(report):
    names={'original':'기존 그림','readable':'개선 그림','code_index':'코드 인덱스만','oracle':'완벽 인식 가정 · 원본 구조 JSON'}
    a,b=report['vision']['original'],report['vision']['readable']
    lines=['# Qwen3-VL 8B: 아키텍처 그림 개선 비교','',
        f"비전 **`{report['visionModel']}`**, 코드 검토 **`{report['reviewModel']}`**로 실측했습니다. "
        '코드 320개 파일과 원본 구조의 구성요소 28개·연결 26개를 유지하고 그림 표현을 변경했습니다. 두 이미지는 3000×2320입니다.','',
        '## 그림에서 변경한 점','',
        '- 구성요소 목록과 연결 관계를 분리했습니다. 각 연결은 독립된 행에 배치해 선 교차를 제거했습니다.',
        '- 화살표 양쪽에 서비스 ID를 반복하고, 기존 그래프의 구성요소 종류를 명시했습니다.',
        '- 역할·기술·그룹·연결 설명·동기/비동기 구분을 보존했습니다. 파일 경로·보안 정답은 추가하지 않았습니다.',
        '- 같은 시스템을 다른 시각 표현으로 나타낸 실험입니다. 좌표만 이동한 실험은 아니며 ID 반복과 종류 명시의 효과가 함께 포함됩니다.','',
        '## 인식 결과: 각 그림 2회','',
        '| 그림 | 유효 응답 | 구성요소 ID 평균 / 28 | 연결 평균 / 26 | 평균 입력 토큰 | 평균 출력 토큰 | 평균 인식 시간(초) |',
        '|---|---:|---:|---:|---:|---:|---:|']
    for name,row in report['vision'].items():
        lines.append(f"| {names[name]} | {row['validRuns']}/2 | {number(row['meanMatchedComponents'])} | {number(row['meanMatchedEdges'])} | {number(row['meanInputTokens'])} | {number(row['meanOutputTokens'])} | {sec(row['meanWallMs'])} |")
    lines.append('| 완벽 인식 가정 · 원본 구조 JSON | 모델 인식 생략 | 28 (가정) | 26 (가정) | 측정 제외 | 측정 제외 | 측정 제외 |')
    lines.extend(['','**완벽 인식 가정**은 원본 그래프의 모든 구성요소·역할·연결을 구조 JSON으로 직접 전달하는 대조군입니다. '
        '그림을 실제로 완벽하게 읽은 측정값이나 0초짜리 비전 호출이 아닙니다. 후속 코드 검색·Ministral 검토는 다른 방식과 동일하게 실측합니다. '
        '그림 자체에 빠진 백그라운드 작업까지 추가하거나 취약점 정답을 전달하지 않습니다.'])
    lines.extend(['','실행 순서는 기존 → 개선 → 개선 → 기존(ABBA)입니다. 모델·프롬프트·이미지 크기·생성 한도를 동일하게 유지했습니다. '
        '구성요소/연결 평균은 유효 응답만의 값이며 실패 횟수를 함께 표시합니다. 시간은 실패를 포함한 두 시도입니다. '
        '2회만으로 통계적 유의성이나 모든 아키텍처에 대한 일반 성능을 주장하지 않습니다.',''])
    if a['validRuns']==2 and b['validRuns']==2:
        difference=b['meanMatchedEdges']-a['meanMatchedEdges']
        lines.append(f"개선 그림의 방향 있는 연결 일치 평균은 기존 대비 **{difference:+.1f}개**입니다. 아래 코드 검색·근거 품질까지 별도로 확인해야 최종 성과를 판단할 수 있습니다.")
    lines.append('')
    for name,row in report['vision'].items():
        for r in row['runs']:
            q=r.get('quality',{})
            extras=str(len(q['unexpectedMappedEdges'])) if 'unexpectedMappedEdges' in q else '—'
            lines.append(f"- {names[name]} · 순서 {r['sequence']}: {'유효 JSON' if r['complete'] else '실패'}, "
                         f"ID {q.get('componentIdentitiesMatched','—')}/28, 연결 {q.get('edgesMatched','—')}/26, "
                         f"추가 연결 {extras}, {sec(r['phaseWallMs'])}초"+
                         (f", 오류 `{r.get('error')}`" if not r['complete'] else '')+'.')
    lines.extend(['','연결 일치는 방향과 양 끝 ID를 대조한 엄격한 지표입니다. 중간 브로커를 생략한 요약도 불일치일 수 있습니다. '
        '역할·보호 수단·법률 준수 정확도는 이 숫자로 평가하지 않습니다. JSON 형식 통과와 구조 정확도는 별개입니다.','',
        '### 응답 원문 진단: 실패 응답도 포함','',
        '다음은 측정 종료 후 원문에 적힌 ID·연결 끝점을 원본 그래프와 직접 대조하는 보조 진단입니다. '
        '구조 검증을 통과하지 못한 응답도 포함하며, 누락을 보정하거나 코드 검색에 전달하지 않습니다. 연결 설명의 정확도까지 평가한 값은 아닙니다.','',
        '| 그림·순서 | 원문 ID 일치 / 28 | 원문 연결 끝점 일치 / 26 | 선언 안 된 끝점 ID 수 | SYNC/ASYNC를 보호수단으로 오분류 |',
        '|---|---:|---:|---:|---:|'])
    for name,row in report['vision'].items():
        for r in row['runs']:
            d=r.get('rawDiagnostic')
            if d:
                lines.append(f"| {names[name]} · {r['sequence']} | {d['literalComponentIdsMatched']} | {d['literalDirectedEndpointsMatched']} | {len(d['undeclaredEndpointIds'])} | {d['modeMisclassifiedAsProtection']} |")
    lines.extend(['',
        '## 후속 코드 검색 및 Ministral 검토','',
        '유효 응답이 있는 그림은 **첫 번째 유효 응답**을 그대로 사용합니다. 두 번 모두 구조 검증에 실패한 개선 그림은 코드 인덱스로 대체했습니다. '
        '점수가 좋은 응답을 골라 쓰거나 사람이 수정하지 않았습니다. '
        '네 방식 모두 기존 파일 선별기·96개 파일/96,000바이트/3단계 연결 예산과 최대 2회 추가 조회를 사용합니다.','',
        '| 방식 | 최초 → 추가조회 파일 | 입력 토큰 | 출력 토큰 | 계획·리뷰 시간(초) | 필수 맥락 / 12 | 원문 근거 / 4 |',
        '|---|---:|---:|---:|---:|---:|---:|'])
    for name,r in report['reviews'].items():
        t=r['totals'] or {}; q=r['quality'] or {}
        label=names[name]+(' (코드로 대체)' if name in ('original','readable') and not r['decision']['useVisionContext'] else '')
        lines.append(f"| {label} | {r['initialFiles']} → {r['effectiveFiles']} | {number(t.get('prompt_eval_count'))} | "
                     f"{number(t.get('eval_count'))} | {sec(r['endToEndWallMs'])} | {q.get('requiredSelected','—')} | {len(q.get('verifiedMatches',[]))} |")
    lines.extend(['','검토 시간에는 최초 이미지 인식이 포함되지 않습니다. 다음 합계는 첫 유효 이미지 인식·JSON 검증·저장과 '
                  '계획·리뷰를 더한 값이며 하나의 통합 요청을 잰 시간은 아닙니다.',''])
    for name in ('original','readable'):
        r=report['reviews'][name]; first=r['firstUse']
        lines.append(f"- **{names[name]}**: 맥락 전달 `{r['decision']['useVisionContext']}`, 선택 사유 `{r['decision']['reason']}`, "
            f"코드 모듈 매핑 {r['mappingCount']['matched']}/{r['mappingCount']['total']}."+
            (f" 첫 사용 합계 {sec(first['wallMs'])}초, 입력 {first['inputTokens']:,}·출력 {first['outputTokens']:,}토큰." if first else ' 이미지 기반 첫 사용 합계 없음.'))
        failed=r['failedFirstAttemptCombined']
        if failed:
            lines.append(f"  첫 인식 실패 시도 + 코드 인덱스로 대체한 검토의 비용은 **{sec(failed['wallMs'])}초**, "
                         f"입력 **{number(failed['inputTokens'])}토큰**입니다. 인식 실패 비용을 0으로 처리하지 않으며, 성공한 구조 기반 검토 시간으로 해석하지 않습니다.")
    oracle=report['reviews']['oracle']
    lines.append(f"- **완벽 인식 가정**: 맥락 전달 `{oracle['decision']['useVisionContext']}`, 선택 사유 `{oracle['decision']['reason']}`, "
                 f"코드 모듈 매핑 {oracle['mappingCount']['matched']}/{oracle['mappingCount']['total']}. "
                 '표의 토큰·시간은 원본 구조 JSON을 포함한 계획·리뷰만의 실측값입니다. 이미지 인식 포함 총시간은 계산하지 않습니다.')
    lines.extend(['','### 구조 인식과 코드 매핑의 별도 한계',''])
    for name in ('original','readable'):
        missing=report['reviews'][name]['unmappedExactServiceIds']
        if missing:
            lines.append(f"- **{names[name]}**: 추출된 ID 중 실제 서비스 폴더명과 같은 **{len(missing)}개**가 모듈 매핑에서는 연결되지 않았습니다. "
                         '현재 선별기는 구성요소 `id` 대신 `label`로 모듈명을 찾습니다. ID와 역할 설명을 분리해 출력한 경우 이 인터페이스 문제가 영향을 줍니다.')
    lines.append('')
    lines.append('완벽 인식 가정 JSON은 구성요소 label에 ID와 역할을 함께 담는 기존 변환기를 사용합니다. '
                 '따라서 실제 Qwen 응답과 이 대조군의 차이에는 인식 정확도뿐 아니라 표현 형식과 현재 매핑 구현의 영향도 포함됩니다. '
                 '이번 고정 실험 중 선별기 구현은 변경하지 않았습니다.')
    lines.extend(['','전체 코드 320개 파일 비교는 [이전 실험](../../RESULTS.md)에 남아 있습니다. 이번 실험에서는 다시 실행하지 않았습니다. '
        '이전 Ministral 비전 결과와 이번 Qwen 결과 사이의 차이를 그림 개선만의 효과로 해석하지 않습니다.','',
        '## 입력 동일성·누락·오류',''])
    for pair in report['comparisons']:
        lines.append(f"- {names[pair['left']]} ↔ {names[pair['right']]}: 최초 요청 동일 `{pair['sameInitialRequests']}`, 전체 요청 동일 `{pair['sameAllRequests']}`.")
    lines.extend(['','최초 요청이 같거나 구조 맥락이 제외된 경우, 검토 시간·출력의 차이를 비전의 추가 효과로 볼 수 없습니다. '
        '검토는 코드 인덱스 → 기존 그림 → 개선 그림 → 완벽 인식 가정 순서로 각 1회이며 캐시를 강제로 비우지 않았습니다.',''])
    for name,r in report['reviews'].items():
        q=r['quality'] or {}; audit=r['responseAudit']
        lines.append(f"- **{names[name]}**: 실행 완료 `{r['complete']}`, 모든 측정 조건 통과 `{r['allMeasuredChecksPass']}`. "
            f"추가 후보 {q.get('extraCandidates','—')}, 정상 함수 오탐 {len(q.get('negativeControlFlags',[]))}, "
            f"잘못된 본문 인용 {q.get('invalidEvidence','—')}, 보조 인용 {audit.get('invalidSupportEvidence','—')}. "
            f"미해결 조회 {len(r['unresolvedNeeds'])}, 거절 조회 {len(r['rejectedNeeds'])}, 후속 응답의 재요청 {len(audit.get('followupResponseNeeds',[]))}.")
        if q.get('missingRequiredContext'):
            lines.append('  누락 파일: '+', '.join(f'`{p}`' for p in q['missingRequiredContext'])+'.')
        if r['missingContextReasons']:
            lines.append('  선택기 기록: '+', '.join(f"`{item['path']}` → `{item['reason']}`" for item in r['missingContextReasons'])+'.')
    lines.extend(['','코드 근거 점수는 지정된 원문 행과 보조 인용 검사입니다. 배치 간 전체 데이터 흐름을 증명하거나 패치를 적용한 결과가 아닙니다. '
        '그림 밖 정기 작업도 계속 채점했습니다. 모델 다운로드·예열·모델 전환·사람의 그림 작성 시간은 표에서 제외했습니다. '
        '로컬 모델 추론 및 합성 데이터 결과이며, 실제 서비스 보안이나 법률 준수를 보증하지 않습니다.','',
        '## 응답 호환성 처리와 초기 실패 기록','',
        'Ollama 0.32.1의 이 로컬 실행에서는 Qwen의 구조 JSON이 `message.content`가 빈 상태로 `message.thinking`에 담겨 반환됐습니다. '
        '최초 content 전용 실험은 중단하고 [초기 실패 기록](../qwen3-vl-8b/preflight-status.json)과 실행기 스냅샷을 보존했습니다. '
        '최종 실험은 content가 비어 있을 때에만 thinking 필드 전체가 동일한 엄격한 구조 JSON 스키마를 만족하는지 확인합니다. '
        '자유 서술에서 JSON을 추출하거나 내용을 고치지 않습니다. 이 호환성 처리를 양쪽 그림에 동일하게 적용한 새 측정입니다.','',
        '## 원본 및 재집계','',
        '- [개선 PNG](../architecture.png) · [확대 가능한 SVG](../architecture.svg) · [그림 정보](../architecture.render.json)',
        '- [고정 프로토콜](protocol.json) · [측정 로그](measurements.jsonl) · [집계 JSON](summary.json)',
        '- [기존 그림 첫 응답](raw/vision-1-original.json) · [개선 그림 첫 응답](raw/vision-2-readable.json)',
        '', '재집계: `.venv/bin/python scripts/summarize_readable_architecture.py`. 모델 호출 없이 원본 파일·응답 해시를 대조하고 집계합니다.'])
    return '\n'.join(lines)+'\n'


def main():
    report=load_report()
    (PUBLIC/'summary.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    (PUBLIC/'RESULTS.md').write_text(render(report))
    print(json.dumps({'vision':{k:{x:v[x] for x in ('validRuns','meanMatchedEdges','meanWallMs')} for k,v in report['vision'].items()},
                      'reviewQuality':{k:v['quality'] for k,v in report['reviews'].items()}},ensure_ascii=False))


if __name__=='__main__':
    main()
