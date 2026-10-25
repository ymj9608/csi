import { test, expect, type Page } from '@playwright/test';

function verifiedResult(){
  const securityChecks=Array.from({length:13},(_,index)=>({id:`check-${index+1}`,status:'PASSED'}));
  const proof={passed:40,failed:0,securityPassed:13,securityTotal:13,suiteVersion:2,securityChecks,skipped:1,exitCode:0};
  return {reason:'전체 정책을 준수하고 기존 계정 문제가 모두 해결되었습니다.',modelLimitations:['bcrypt로 생성된 해쉬는 레거시 계정과 호환되지 않습니다.'],citedIds:['finding'],baseline:{passed:30,failed:10,securityPassed:3,securityTotal:13,suiteVersion:2,skipped:1},verification:proof,durationMs:60000,attempts:[{number:1,generationMs:45000,verification:proof}],limitations:[],files:[{path:'backend/app/core/csi_signup.py',diff:'--- a/signup.py\n+++ b/signup.py\n+import bcrypt\n'}],review:{version:1,summary:'신규 비밀번호 저장과 로그 노출 개선을 테스트로 확인했습니다.',changes:[{id:'password',title:'신규 계정 비밀번호 저장',before:'공통 Salt와 빠른 SHA-256 해시를 사용했습니다.',after:'bcrypt 비용 12와 개별 무작위 Salt를 사용합니다.',status:'VERIFIED',tests:['check-1','check-2'],evidenceIds:['reference']},{id:'login',title:'기존·신규 계정 로그인',before:'SHA-256 실습 계정을 인증합니다.',after:'기존 SHA-256 계정과 신규 bcrypt 계정을 모두 인증합니다.',status:'VERIFIED',tests:['check-3']}],remainingRisks:[{id:'migration',title:'기존 계정 해시 전환',detail:'기존 SHA-256 해시는 그대로 남습니다.',nextStep:'로그인 성공 후 재해시하는 기능이 필요합니다.'},{id:'logs',title:'과거 민감정보 로그',detail:'이미 남은 로그는 삭제되지 않습니다.',nextStep:'보존 정책에 따라 정리 대상을 확인하세요.'}],scope:['Lichu 회원가입 실습 경로를 SQLite로 테스트했습니다.','PostgreSQL 동시성과 실제 배포는 검증하지 않았습니다.']}};
}

for(const broken of [false,true])test(`project profile verification ${broken?'rejects stale candidate':'allows complete required checks'}`,async({page})=>{
  const result:any=verifiedResult();delete result.review;
  const ids=['tests/test_privacy.py::test_no_values','tests/test_privacy.py::test_event','tests/test_db.py::test_postgres'];
  result.schemaVersion=2;result.engineVersion='5';result.planDigest='a'.repeat(64);result.sourceManifestDigest='b'.repeat(64);
  result.testInventory=ids;result.allowedSkips=[ids[2]];
  result.files[0].afterSha256='c'.repeat(64);
  result.verification={exitCode:0,passed:2,failed:0,skipped:1,securityTotal:2,securityPassed:2,
    planDigest:result.planDigest,sourceManifestDigest:result.sourceManifestDigest,candidateSha256:(broken?'d':'c').repeat(64),
    checks:ids.map((id,i)=>({id,status:i===2?'SKIP':'PASS'}))};
  await mockFlow(page,'SEC-05',{status:'READY',result});
  await page.getByRole('tab',{name:'수정안 생성·검토',exact:true}).click();
  const region=page.getByRole('region',{name:'코딩 Agent 수정안'});
  await expect(region).toContainText(broken?'프로젝트 검증 미완료':'프로젝트 검증 통과');
  const approve=region.getByRole('button',{name:'검토 후 승인',exact:true});
  if(broken)await expect(approve).toBeDisabled();else await expect(approve).toBeEnabled();
  await region.getByText('고정 테스트별 결과',{exact:true}).click();
  await expect(region).toContainText('tests/test_db.py::test_postgres');
});

test('saved unified VLM instruction is displayed as text without another orchestration trace',async({page})=>{
  const result:any=verifiedResult();
  result.handoff={mode:'unified-vlm-review-v1',model:'qwen3-vl:8b',status:'READY',reusedScanAnalysis:true,
    instruction:'<img src=x onerror="window.injected=true"> 내부 데이터와 이벤트를 보존하고 외부 전송만 수정하세요.'};
  await mockFlow(page,'SEC-05',{status:'READY',result});
  await page.getByRole('tab',{name:'수정안 생성·검토',exact:true}).click();
  const region=page.getByRole('region',{name:'코딩 Agent 수정안'});
  await expect(region).toContainText('qwen3-vl:8b · 저장된 통합 분석');
  await expect(region.getByText('저장된 VLM 자연어 수정 지시',{exact:true})).toBeVisible();
  await expect(region.locator('pre').filter({hasText:'onerror'})).toContainText('<img src=x');
  await expect(region.getByText('VLM 총괄 작업 기록',{exact:true})).toHaveCount(0);
  expect(await page.evaluate(()=>(window as any).injected)).toBeUndefined();
});

test('OpenAI orchestration trace is visible and model text is escaped',async({page})=>{
  const result:any=verifiedResult();
  result.handoff={mode:'vlm-orchestrator-v1',provider:'openai',model:'gpt-6.1-sol',sourceCommitMatches:null,
    metrics:{wallDurationMs:90000,apiDurationMs:20000,inputTokens:14000,outputTokens:1800,reasoningTokens:500},
    trace:[{turn:1,tool:'read_code',status:'OK',path:'backend/app/core/csi_signup.py'},
      {turn:2,tool:'delegate_coding',status:'OK',attempt:1,instruction:'<img src=x onerror="window.injected=true"> 비밀번호 저장을 보완하세요.'},
      {turn:3,tool:'run_verification',status:'OK',attempt:1},{turn:4,tool:'finish_review',status:'OK'}],
    conclusion:'격리 테스트 통과를 확인했습니다. 기존 데이터 정리와 관리자 승인은 별도입니다.'};
  const {state}=await mockFlow(page,'SEC-02',{status:'READY',result});
  await page.getByRole('tab',{name:'수정안 생성·검토',exact:true}).click();
  const region=page.getByRole('region',{name:'코딩 Agent 수정안'});
  await expect(region).toContainText('gpt-6.1-sol · OpenAI 총괄');
  await expect(region.getByText('VLM 총괄 작업 기록',{exact:true})).toBeVisible();
  await expect(region).toContainText('입력 14000 / 출력 1800 토큰');
  await region.getByText('1차 수정 지시문',{exact:true}).click();
  await expect(region.locator('pre').filter({hasText:'onerror'})).toContainText('<img src=x');
  await expect(region.locator('img')).toHaveCount(0);
  expect(state.decisions).toEqual([]);
  await expect(region.getByRole('button',{name:'검토 후 승인',exact:true})).toBeEnabled();
  await page.setViewportSize({width:390,height:844});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
});

async function mockFlow(page:Page, rule='SEC-02', initial?:{status:string;result:any;progress?:any}) {
  const finding:any={id:'finding',scanId:'scan',repository:'ymj9608/Lichu',ruleId:rule,title:'비밀번호 저장 보완',status:'OPEN',severity:'HIGH',evidenceStatus:'SUSPECTED',confidence:'MEDIUM',filePath:rule==='POL-01'?'backend/app/models/entities.py':'backend/app/core/csi_signup.py',startLine:1,endLine:2,commitSha:'a'.repeat(40),maskedCodeEvidence:'hashlib.sha256(password.encode())',analysis:{red:'빠른 해시 저장 위험',blue:'회원가입 경로 확인',references:[{chunkId:'reference',sectionId:'POL-04',sectionTitle:'비밀번호 저장 정책',documentId:'POLICY',documentVersion:'1',pageNumber:4,content:'bcrypt 비용 12와 개별 salt를 사용합니다.'}]}};
  const result=verifiedResult();
  const state:any={job:initial?{id:'proposal',createdAt:new Date().toISOString(),commitSha:'a'.repeat(40),...initial}:null,requests:0,decisions:[]};
  await page.route('**/api/**',async route=>{
    const request=route.request(),path=new URL(request.url()).pathname;
    let value:any={};
    if(path.endsWith('/stream'))return route.fulfill({status:200,contentType:'text/event-stream',body:': no update events\n\n'});
    if(path==='/api/auth/me')value={username:'test',role:'SECURITY_REVIEWER'};
    else if(path==='/api/auth/csrf')value={token:'mock-csrf'};
    else if(path==='/api/findings/finding')value=finding;
    else if(path==='/api/scans/scan')value={id:'scan',status:'COMPLETED'};
    else if(path==='/api/scans/scan/findings')value=[finding];
    else if(path==='/api/scans/scan/coding-proposals'){
      if(request.method()==='POST'){
        state.requests++;state.job={id:'proposal',status:'RUNNING',createdAt:new Date().toISOString(),commitSha:'a'.repeat(40),progress:{phase:'GENERATING',attempt:1}};value=state.job;
      }else value={enabled:true,supported:true,verificationProfile:{version:1,config:{profileId:'test-profile',editablePaths:['backend/app/core/csi_signup.py'],ruleIds:['SEC-02','SEC-03','SEC-05'],inventory:[]}},items:state.job?[state.job]:[]};
    }else if(path==='/api/coding-proposals/proposal/decision'){
      state.decisions.push(request.postDataJSON().decision);state.job.status=request.postDataJSON().decision;value={status:state.job.status};
    }
    await route.fulfill({json:value});
  });
  await page.goto('/findings/finding');
  return {state,result};
}

test('architecture context remains visible after the fast lookup phase and escapes extracted text',async({page})=>{
  const note='저장된 아키텍처 관련 후보: <img src=x onerror="window.injected=true"> Signup demo';
  await mockFlow(page,'SEC-02',{status:'RUNNING',result:null,progress:{phase:'GENERATING',attempt:1,architectureNote:note}});
  await page.getByRole('tab',{name:'수정안 생성·검토',exact:true}).click();
  const region=page.getByRole('region',{name:'코딩 Agent 수정안'});
  await expect(region.getByTestId('architecture-context')).toHaveText(note);
  await expect(region).toContainText('VLM 지시에 따른 로컬 코드 생성');
  await expect(region.getByTestId('architecture-context').locator('img')).toHaveCount(0);
});

test('risk analysis → generate → progress polling without SSE → evidence → approve',async({page})=>{
  const {state,result}=await mockFlow(page);
  const riskText=page.locator('.verdict.red').getByText('빠른 해시 저장 위험',{exact:true});
  await expect(riskText).toBeVisible();
  await expect(riskText).toHaveText('빠른 해시 저장 위험');
  await page.getByRole('button',{name:'수정안 생성·검토로 이동',exact:true}).click();
  const region=page.getByRole('region',{name:'코딩 Agent 수정안'});
  await region.getByRole('button',{name:'수정안 생성 요청',exact:true}).click();
  await expect.poll(()=>state.requests).toBe(1);
  await expect(region).toContainText('VLM 지시에 따른 로컬 코드 생성');
  await expect(region.getByRole('button',{name:'검토 후 승인',exact:true})).toHaveCount(0);
  state.job={...state.job,status:'READY',result};
  await expect(region).toContainText('수정안 검증 완료 · 관리자 검토 대기',{timeout:12000});
  await expect(region.getByRole('heading',{name:'수정 전후 개선 사항',exact:true})).toBeVisible();
  await expect(region.locator('.coding-check-passed')).toHaveCount(2);
  await expect(region.getByText('전체 정책을 준수하고 기존 계정 문제가 모두 해결되었습니다.',{exact:true})).not.toBeVisible();
  await expect(region).toContainText('기존 SHA-256 해시는 그대로 남습니다.');
  await expect(region).toContainText('이미 남은 로그는 삭제되지 않습니다.');
  await expect(region).toContainText('원본 반영 여부는 별도 확인 필요');
  await expect(region.locator('tr').filter({hasText:'추가 보안 검증'})).toContainText('13 / 13');
  await expect(region).toContainText('수정 근거 확인');
  await expect(region.getByText('근거: POL-04',{exact:true})).toBeVisible();
  await region.getByText('POL-04 · 비밀번호 저장 정책',{exact:true}).click();
  await expect(region.getByText('bcrypt 비용 12와 개별 salt를 사용합니다.',{exact:true})).toBeVisible();
  await expect(region.locator('.coding-diff')).toContainText('import bcrypt');
  await page.screenshot({path:'../.runtime/coding-review-ui/desktop.png',fullPage:true,animations:'disabled'});
  await page.setViewportSize({width:390,height:844});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  await page.screenshot({path:'../.runtime/coding-review-ui/mobile.png',fullPage:true,animations:'disabled'});
  await region.getByRole('button',{name:'검토 후 승인',exact:true}).click();
  await expect(region).toContainText('수정안 승인됨');
  await expect(region).toContainText('원본 반영 여부는 별도 확인 필요');
  expect(state.decisions).toEqual(['APPROVED']);
});

test('failed result stays unapprovable and successful retry can be rejected',async({page})=>{
  const {state,result}=await mockFlow(page);
  await page.getByRole('tab',{name:'수정안 생성·검토',exact:true}).click();
  const region=page.getByRole('region',{name:'코딩 Agent 수정안'});
  await region.getByRole('button',{name:'수정안 생성 요청',exact:true}).click();
  await expect(region).toContainText('VLM 지시에 따른 로컬 코드 생성');
  state.job={...state.job,status:'BLOCKED',result:{...result,verification:undefined,files:[],failureReason:'UNDEFINED_GLOBAL',lastVerification:{passed:29,failed:5,securityPassed:3,skipped:1},attempts:[{number:1,error:'UNDEFINED_GLOBAL',generationMs:40000}]}};
  await expect(region).toContainText('수정안 작업이 중단되었습니다.',{timeout:12000});
  await expect(region.locator('.coding-check-passed')).toHaveCount(0);
  await expect(region.getByText('신규 비밀번호 저장과 로그 노출 개선을 테스트로 확인했습니다.',{exact:true})).toHaveCount(0);
  await expect(region.getByRole('button',{name:'검토 후 승인',exact:true})).toHaveCount(0);
  await expect(region.locator('tr').filter({hasText:'실패'})).toContainText('5');
  await region.getByRole('button',{name:'새 수정안 요청',exact:true}).click();
  await expect.poll(()=>state.requests).toBe(2);
  await expect(region).toContainText('VLM 지시에 따른 로컬 코드 생성');
  state.job={...state.job,status:'READY',result};
  await expect(region.getByRole('button',{name:'거절',exact:true})).toBeVisible({timeout:12000});
  await region.getByRole('button',{name:'거절',exact:true}).click();
  await expect(region).toContainText('수정안 거절됨');
  expect(state.decisions).toEqual(['REJECTED']);
});

test('unrelated risk cannot generate the signup remediation',async({page})=>{
  await mockFlow(page,'POL-01');
  await page.getByRole('tab',{name:'수정안 생성·검토',exact:true}).click();
  const region=page.getByRole('region',{name:'코딩 Agent 수정안'});
  await expect(region).toContainText('이 항목에 적용 가능한 검증 프로필이 없습니다');
  await expect(region.getByRole('button',{name:'수정안 생성 요청',exact:true})).toHaveCount(0);
});

test('old seven-check results keep their original scope and model claims stay collapsed',async({page})=>{
  const result:any=verifiedResult();
  delete result.review;
  result.verification={passed:34,failed:0,securityPassed:7,skipped:1};
  result.baseline={passed:30,failed:4,securityPassed:3,skipped:1};
  result.attempts=[{number:1,verification:result.verification}];
  await mockFlow(page,'SEC-02',{status:'READY',result});
  await page.getByRole('tab',{name:'수정안 생성·검토',exact:true}).click();
  const region=page.getByRole('region',{name:'코딩 Agent 수정안'});
  await expect(region).toContainText('이전 검증 결과 · 관리자 검토 대기');
  await expect(region).toContainText('새 검증을 실행한 결과가 아닙니다.');
  await expect(region.locator('tr').filter({hasText:'추가 보안 검증'})).toContainText('7 / 7');
  await expect(region.locator('.coding-check-passed')).toHaveCount(0);
  await expect(region.getByText(result.modelLimitations[0],{exact:true})).not.toBeVisible();
  await region.getByText('AI 설명 · 테스트로 확인된 사실과 별도',{exact:true}).click();
  await expect(region.getByText(result.modelLimitations[0],{exact:true})).toBeVisible();
});

for(const status of ['SKIPPED','FAILED','ERROR'])test(`${status} security check cannot be shown as verified even if READY`,async({page})=>{
  const result=verifiedResult();
  result.verification.securityChecks[0]!.status=status;
  await mockFlow(page,'SEC-02',{status:'READY',result});
  await page.getByRole('tab',{name:'수정안 생성·검토',exact:true}).click();
  const region=page.getByRole('region',{name:'코딩 Agent 수정안'});
  await expect(region).toContainText('검증 기록 확인 필요');
  await expect(region.locator('.coding-check-passed')).toHaveCount(0);
  await expect(region.getByRole('button',{name:'검토 후 승인',exact:true})).toBeDisabled();
});

test('missing verification evidence cannot turn a model claim into a verified change',async({page})=>{
  const result=verifiedResult();
  result.review.changes[0]!.tests=['unknown-test'];
  result.review.changes[1]!.tests=[];
  result.attempts=[{number:1,generationMs:45000} as any];
  await mockFlow(page,'SEC-02',{status:'READY',result});
  await page.getByRole('tab',{name:'수정안 생성·검토',exact:true}).click();
  const region=page.getByRole('region',{name:'코딩 Agent 수정안'});
  await expect(region.locator('.coding-check-passed')).toHaveCount(0);
  await expect(region.locator('.coding-check')).toHaveText(['확인 필요','확인 필요']);
  await expect(region).toContainText('1차 생성 · 검증 기록 없음');
  await expect(region.getByText(result.review.summary,{exact:true})).toHaveCount(0);
  await expect(region.getByRole('button',{name:'검토 후 승인',exact:true})).toBeDisabled();
});

test('a failed legacy verification cannot authorize approval',async({page})=>{
  const result:any=verifiedResult();
  delete result.review;
  result.verification={passed:30,failed:4,securityPassed:3,skipped:1,exitCode:1};
  result.baseline={passed:30,failed:4,securityPassed:3,skipped:1};
  await mockFlow(page,'SEC-02',{status:'READY',result});
  await page.getByRole('tab',{name:'수정안 생성·검토',exact:true}).click();
  const region=page.getByRole('region',{name:'코딩 Agent 수정안'});
  await expect(region.getByRole('button',{name:'검토 후 승인',exact:true})).toBeDisabled();
  await expect(region).toContainText('최종 검증 기록이 완전하지 않아 승인할 수 없습니다.');
});

test('direct VLM planning progress and literal work order remain separate from approval',async({page})=>{
  const {state,result}=await mockFlow(page);
  await page.getByRole('tab',{name:'수정안 생성·검토',exact:true}).click();
  const region=page.getByRole('region',{name:'코딩 Agent 수정안'});
  state.job={id:'proposal',architectureId:'image-id',status:'RUNNING',createdAt:new Date().toISOString(),progress:{phase:'VLM_PLANNING',attempt:0}};
  await page.getByRole('button',{name:'새로고침',exact:true}).click();
  await expect(region).toContainText('VLM이 근거와 실행 결과를 검토하고 다음 작업 결정');
  await expect(region.getByRole('button',{name:'검토 후 승인',exact:true})).toHaveCount(0);
  state.job={...state.job,status:'READY',result:{...result,handoff:{mode:'vlm-direct-v1',sourceCommitMatches:null,
    instruction:'코딩 Agent에게: <script>throw Error("must remain text")</script> 근거를 확인하세요.',
    metrics:{wallDurationMs:2000,prompt_eval_count:100,eval_count:50}}}};
  await page.getByRole('button',{name:'새로고침',exact:true}).click();
  await region.getByText('아키텍처·정책 기반 수정 지시문',{exact:true}).click();
  await expect(region).toContainText('이미지의 기준 커밋은 미확인');
  await expect(region).toContainText('<script>throw Error("must remain text")</script>');
  await expect(region.locator('script')).toHaveCount(0);
  expect(state.decisions).toEqual([]);
});
