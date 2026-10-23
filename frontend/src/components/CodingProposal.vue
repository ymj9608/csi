<script setup lang="ts">
import { computed, ref, watch, onMounted, onBeforeUnmount } from 'vue';
import { api, date } from '../lib/api';
import { readReview, securityCount, finalVerificationPassed, previousVerificationPassed, changeVerified } from '../lib/codingReview';
import type { ReviewChange } from '../lib/codingReview';
import { generationBlockedReason } from '../lib/analysisStatus';
const props=defineProps<{scanId:string; scanStatus:string; coding:any; findings?:any[]; finding?:any}>();
const emit=defineEmits<{refresh:[]}>();
const busy=ref(false),error=ref('');
const snapshot=ref(props.coding),now=ref(Date.now()),pollError=ref('');
watch(()=>props.coding,value=>{if(value)snapshot.value=value;});
watch(()=>props.scanId,()=>{snapshot.value=props.coding;pollError.value='';});
const state=computed(()=>snapshot.value);
const latest=computed(()=>state.value?.items?.[0]);
const result=computed(()=>latest.value?.result);
const review=computed(()=>readReview(result.value?.review));
const verified=computed(()=>finalVerificationPassed(result.value,latest.value?.status));
const verifiedSummary=computed(()=>verified.value && !!review.value?.changes.length &&
  review.value.changes.every(change=>changeVerified(change,result.value,latest.value?.status)));
const legacyResult=computed(()=>{
  const saved=result.value?.verification || result.value?.lastVerification || result.value?.baseline;
  return !result.value?.review && Number.isInteger(saved?.securityPassed) && saved?.suiteVersion==null && saved?.securityTotal==null;
});
const canApprove=computed(()=>latest.value?.status==='READY' && (legacyResult.value && previousVerificationPassed(result.value) || verifiedSummary.value));
const supported=computed(()=>state.value?.supported && (!props.finding ||
  (props.finding.filePath==='backend/app/core/csi_signup.py' && ['SEC-02','SEC-03','SEC-05'].includes(props.finding.ruleId))));
const active=computed(()=>['QUEUED','RUNNING'].includes(latest.value?.status));
const generationBlocked=computed(()=>generationBlockedReason(props.scanStatus));
const elapsedSeconds=computed(()=>Math.max(0,Math.floor((now.value-Date.parse(latest.value?.createdAt||''))/1000)));
const checks=computed(()=>result.value?.verification || result.value?.lastVerification ||
  [...(result.value?.attempts||[])].reverse().find((a:any)=>a.verification)?.verification);
const phaseNames:Record<string,string>={ARCHITECTURE_CONTEXT:'아키텍처 참고',BASELINE:'수정 전 테스트',GENERATING:'모델 코드 생성',VALIDATING:'코드 범위·구문 검사',VERIFYING:'수정 후 기능·보안 테스트',RETRYING:'검증 오류를 반영한 재생성 준비'};
const errors:Record<string,string>={IMPORT_NOT_ALLOWED:'허용되지 않은 모듈 참조',UNDEFINED_GLOBAL:'필요한 import 또는 정의 누락',LEGACY_USES_NEW_HASH:'기존 계정 로그인 호환성 위반',TESTS_FAILED:'기능·보안 테스트 미통과',EVIDENCE_IDS:'근거 인용 검증 실패',MODEL_RESPONSE_FAILED:'모델 응답 처리 실패',OUTPUT_TRUNCATED:'모델 응답 길이 초과',LOGGING_CONFIG_NOT_ALLOWED:'로그 시스템 비활성화·설정 변경 금지',BASELINE_NOT_SUPPORTED:'지원하는 수정 전 코드·검증 환경과 다름',WORKER_LEASE_EXPIRED:'제한 시간 안에 Worker 결과를 받지 못했습니다',VERIFIER_UNAVAILABLE:'격리 테스트 환경에 연결할 수 없습니다',COMMIT_OR_SOURCE_UNAVAILABLE:'검사 커밋 또는 소스를 찾을 수 없습니다',LOCAL_RESULT_STORAGE_FAILED:'생성 결과를 로컬 파일에 저장하지 못했습니다',RETRIEVED_EVIDENCE_REQUIRED:'수정안을 뒷받침할 검색 근거가 없습니다',PROFILE_POLICY_MISMATCH:'현재 지원하는 정책 설정과 다릅니다',WORKER_FAILED:'Worker 실행 중 오류가 발생했습니다'};
const evidenceIds=computed(()=>[...new Set<string>([...(result.value?.citedIds||[]),...(review.value?.changes.flatMap(change=>change.evidenceIds||[])||[])])]);
const citedFindings=computed(()=>(props.findings||[]).filter(f=>evidenceIds.value.includes(f.id)));
const citedReferences=computed(()=>{
  const refs=new Map<string,any>();
  for(const f of props.findings||[])for(const r of f.analysis?.references||[])
    if(evidenceIds.value.includes(r.chunkId))refs.set(r.chunkId,r);
  return [...refs.values()];
});
function evidenceLabels(change:ReviewChange){
  const ids=change.evidenceIds||[];
  return [...new Set([...citedFindings.value.filter(f=>ids.includes(f.id)).map(f=>f.ruleId),
    ...citedReferences.value.filter(r=>ids.includes(r.chunkId)).map(r=>r.sectionId||r.documentId)])].join(' · ');
}
let timer:ReturnType<typeof setInterval>|undefined,polling=false,lastPoll=0;
async function refresh(){
  if(polling)return;
  const scan=props.scanId;polling=true;
  try{const value=await api(`/scans/${scan}/coding-proposals`);if(scan===props.scanId){snapshot.value=value;pollError.value='';}}
  catch{pollError.value='상태 갱신이 지연되고 있습니다. 연결되면 다시 확인합니다.';}
  finally{polling=false;}
}
onMounted(()=>{timer=setInterval(()=>{
  now.value=Date.now();
  if(active.value && now.value-lastPoll>=5000){lastPoll=now.value;void refresh();}
},1000);});
onBeforeUnmount(()=>clearInterval(timer));
const names:Record<string,string>={QUEUED:'로컬 Worker 대기',RUNNING:'수정안 생성·검증 중',BLOCKED:'검증 미통과',FAILED:'작업 실패',APPROVED:'수정안 승인됨',REJECTED:'수정안 거절됨'};
const statusName=computed(()=>latest.value?.status==='READY'
  ? verified.value ? '수정안 검증 완료 · 관리자 검토 대기' : legacyResult.value ? '이전 검증 결과 · 관리자 검토 대기' : '검증 기록 확인 필요'
  : names[latest.value?.status]||latest.value?.status);
function attemptStatus(attempt:any){
  if(attempt.error)return errors[attempt.error]||attempt.error;
  const verification=attempt.verification;
  if(!verification)return '검증 기록 없음';
  if(verification.exitCode!=null && verification.exitCode!==0 || verification.failed>0)return '검증 미통과';
  if(verification.suiteVersion===2)return finalVerificationPassed({verification},'READY') ? '검증 통과' : '검증 확인 필요';
  return verification.failed===0 ? '이전 기준 검사 통과' : '검증 확인 필요';
}
async function action(path:string,body?:unknown){
  busy.value=true;error.value='';
  try{await api(path,'POST',body);await refresh();emit('refresh');}catch(e:any){error.value=e.message;}finally{busy.value=false;}
}
function download(){
  if(latest.value?.status!=='APPROVED')return;
  const text=(result.value?.files||[]).map((f:any)=>f.diff).join('\n');
  const url=URL.createObjectURL(new Blob([text],{type:'text/plain;charset=utf-8'}));
  const a=document.createElement('a');a.href=url;a.download=`csi-${latest.value.id}.patch`;a.click();URL.revokeObjectURL(url);
}
</script>
<template>
  <section class="panel coding-proposal" aria-label="코딩 Agent 수정안">
    <div class="panel-title"><h2>코딩 Agent 수정안</h2><span>Ministral 3 8B · 로컬 실행</span></div>
    <p v-if="!state" role="status">코딩 Agent 상태를 확인하고 있습니다.</p>
    <p v-else-if="!state.enabled">코딩 Agent가 비활성화되어 있습니다.</p>
    <p v-else-if="!supported">이 항목의 자동 수정안은 아직 지원하지 않습니다. 현재는 Lichu 회원가입 실습 코드의 비밀번호 저장·로그 보완을 지원합니다.</p>
    <template v-else>
      <p v-if="!latest">완료된 검사의 커밋을 기준으로 수정안을 생성하고, 별도 공간에서 보안·기능 테스트를 실행합니다.</p>
      <p v-if="finding" class="coding-note">같은 검사에서 발견한 회원가입 비밀번호·로그 문제를 하나의 수정안으로 함께 검토합니다.</p>
      <template v-if="!latest || ['FAILED','BLOCKED','REJECTED'].includes(latest.status)">
        <button :disabled="busy || !!generationBlocked" :aria-describedby="generationBlocked ? `generation-blocked-${scanId}` : undefined" @click="action(`/scans/${scanId}/coding-proposals`)">{{ latest ? '새 수정안 요청' : '수정안 생성 요청' }}</button>
        <div v-if="generationBlocked" :id="`generation-blocked-${scanId}`" role="status">
          <p>{{generationBlocked}}</p>
          <RouterLink :to="`/scans/${scanId}`">검사 상세·실행 기록 확인</RouterLink>
        </div>
      </template>
      <template v-if="latest">
        <p role="status"><strong>{{statusName}}</strong> · {{date(latest.createdAt)}}</p>
        <p v-if="latest.status==='QUEUED'">Mac에서 코딩 Worker가 연결되면 시작합니다.</p>
        <p v-if="active" role="status">경과 {{elapsedSeconds}}초<span v-if="latest.progress?.phase"> · {{latest.progress.attempt ? `${latest.progress.attempt}차 / 최대 2차 · ` : ''}}{{phaseNames[latest.progress.phase]||latest.progress.phase}}<template v-if="latest.progress.note"> ({{latest.progress.note}})</template></span></p>
        <p v-if="latest.status==='RUNNING'" class="coding-note">생성과 테스트를 순서대로 수행합니다. 검증 오류가 있으면 최대 한 번 보완하며, 5초마다 상태를 확인합니다.</p>
        <p v-if="latest.status==='BLOCKED'" class="coding-error">수정안 검증에 실패했습니다. {{errors[result?.failureReason] || '아래 생성 차수별 실패 원인을 확인하세요.'}} 검증을 통과한 코드만 승인할 수 있습니다.</p>
        <p v-if="latest.errorCode" class="coding-error">{{errors[latest.errorCode] || latest.errorCode}} · Worker 연결과 검사 커밋을 확인한 뒤 다시 요청할 수 있습니다.</p>
        <template v-if="result">
          <div class="coding-application"><strong>원본 반영 여부는 별도 확인 필요</strong><p>아래 결과는 별도 공간에서 수정안을 테스트한 기록입니다. 승인만으로 원본 코드나 기존 계정·로그가 변경되지는 않습니다.</p></div>
          <section v-if="review" class="coding-review" aria-label="수정 전후 개선 사항">
            <h3>수정 전후 개선 사항</h3>
            <p v-if="verifiedSummary">{{review.summary}}</p>
            <p v-else class="coding-note">검증이 완료되지 않았습니다. 아래 내용은 보완 목표이며, 실제 개선 여부를 확인해야 합니다.</p>
            <article v-for="change in review.changes" :key="change.id" class="coding-change">
              <div class="coding-change-heading"><h4>{{change.title}}</h4><span :class="['coding-check',{'coding-check-passed':changeVerified(change,result,latest.status)}]">{{changeVerified(change,result,latest.status) ? '테스트로 확인' : '확인 필요'}}</span></div>
              <dl class="coding-comparison"><div><dt>수정 전</dt><dd>{{change.before}}</dd></div><div><dt>{{changeVerified(change,result,latest.status) ? '수정 후' : '수정 목표 · 검증 미완료'}}</dt><dd>{{change.after}}</dd></div></dl>
              <p v-if="evidenceLabels(change)" class="coding-note">근거: {{evidenceLabels(change)}}</p>
              <details v-if="change.tests.length" class="coding-test-evidence"><summary>연결된 보안 검사 {{change.tests.length}}개</summary><ul><li v-for="id in change.tests" :key="id"><code>{{id}}</code></li></ul></details>
            </article>
            <div v-if="review.remainingRisks.length" class="coding-remaining"><h3>아직 남아 있는 작업</h3><article v-for="risk in review.remainingRisks" :key="risk.id"><h4>{{risk.title}}</h4><p>{{risk.detail}}</p><p><strong>다음 조치:</strong> {{risk.nextStep}}</p></article></div>
            <div v-if="review.scope.length" class="coding-scope"><h3>이번 검증 범위</h3><ul><li v-for="scope in review.scope" :key="scope">{{scope}}</li></ul></div>
          </section>
          <div v-else class="coding-legacy"><strong>{{legacyResult ? '이전 검증 기준으로 생성된 결과입니다.' : '검증 요약을 확인할 수 없습니다.'}}</strong><p>항목별 개선 사항과 남은 작업을 구분한 검증 요약이 없습니다. 아래 숫자는 저장된 검사 기록이며, 새 검증을 실행한 결과가 아닙니다. 최신 기준으로 확인하려면 새 수정안 생성이 필요합니다.</p><p>기존 계정 해시 전환, 과거 로그 정리, 운영 환경 적용 여부는 이 결과로 확인되지 않습니다.</p></div>
          <h3 v-if="result.baseline">테스트 실행 결과</h3>
          <table v-if="result.baseline"><thead><tr><th>실행 결과</th><th>수정 전</th><th>수정 후</th></tr></thead>
            <tbody><tr><th>통과</th><td>{{result.baseline.passed}}</td><td>{{checks?.passed ?? '미실행'}}</td></tr>
              <tr><th>실패</th><td>{{result.baseline.failed}}</td><td>{{checks?.failed ?? '—'}}</td></tr>
              <tr><th>추가 보안 검증</th><td>{{securityCount(result.baseline)}}</td><td>{{checks ? securityCount(checks) : '미실행'}}</td></tr>
              <tr><th>건너뜀</th><td>{{result.baseline.skipped}}</td><td>{{checks?.skipped ?? '—'}}</td></tr></tbody>
          </table>
          <p v-if="checks?.skipped" class="coding-note">건너뛴 검사는 통과에 포함하지 않습니다. 운영 환경과 전체 보안·정책 준수는 별도 검토가 필요합니다.</p>
          <p>대상 커밋 <code>{{latest.commitSha}}</code><span v-if="Number.isFinite(result.durationMs)"> · 총 {{(result.durationMs/1000).toFixed(1)}}초</span></p>
          <p v-if="latest.status==='READY' && !canApprove" class="coding-error">최종 검증 기록이 완전하지 않아 승인할 수 없습니다.</p>
          <template v-if="!review"><p v-for="note in result.limitations" :key="note" class="coding-note">{{note}}</p></template>
          <details v-if="result.reason || result.modelLimitations?.length" class="coding-model-explanation"><summary>AI 설명 · 테스트로 확인된 사실과 별도</summary><p class="coding-note">모델이 작성한 설명입니다. 위의 검증 결과와 남은 작업을 기준으로 판단하세요.</p><p v-if="result.reason">{{result.reason}}</p><ul v-if="result.modelLimitations?.length"><li v-for="note in result.modelLimitations" :key="note">{{note}}</li></ul></details>
          <details v-for="attempt in result.attempts" :key="attempt.number"><summary>{{attempt.number}}차 생성 · {{attemptStatus(attempt)}}</summary>
            <p>생성 {{((attempt.generationMs||0)/1000).toFixed(1)}}초</p><p v-for="test in attempt.verification?.failedTests" :key="test">{{test}}</p>
          </details>
          <div v-if="evidenceIds.length" class="coding-evidence">
            <h3>수정 근거 확인</h3>
            <p v-for="f in citedFindings" :key="f.id">{{f.ruleId}} · {{f.title}} · {{f.filePath}}</p>
            <details v-for="r in citedReferences" :key="r.chunkId"><summary>{{r.sectionId}} · {{r.sectionTitle || r.documentId}}</summary>
              <p>{{r.documentId}} · v{{r.documentVersion}} · {{r.pageNumber}}쪽</p><blockquote>{{r.content}}</blockquote>
            </details>
            <details><summary>연결된 근거 ID</summary><ul><li v-for="ref in evidenceIds" :key="ref"><code>{{ref}}</code></li></ul></details>
          </div>
          <div v-for="file in result.files" :key="file.path"><h3>{{file.path}}</h3><pre class="coding-diff"><code>{{file.diff}}</code></pre></div>
        </template>
        <div v-if="latest.status==='READY'" class="coding-actions">
          <button :disabled="busy || !canApprove" @click="action(`/coding-proposals/${latest.id}/decision`,{decision:'APPROVED'})">검토 후 승인</button>
          <button :disabled="busy" @click="action(`/coding-proposals/${latest.id}/decision`,{decision:'REJECTED'})">거절</button>
        </div>
        <template v-if="latest.status==='APPROVED'"><p>{{latest.decidedBy}} · {{date(latest.decidedAt)}} 승인. 코드 반영 전 대상 커밋을 다시 확인해야 합니다.</p><button @click="download">승인한 수정안 다운로드</button></template>
        <p class="coding-note">승인은 수정안에 대한 결정입니다. 코드가 자동으로 병합되거나 배포되지는 않습니다.</p>
      </template>
    </template>
    <p v-if="error" role="alert" class="coding-error">{{error}}</p>
    <p v-if="pollError" role="alert" class="coding-error">{{pollError}}</p>
  </section>
</template>
<style scoped>
.coding-proposal{display:grid;gap:14px;min-width:0}.coding-proposal>div{min-width:0}.coding-proposal p{margin:0;line-height:1.65}.coding-proposal table{text-align:left;border-collapse:collapse;width:100%}.coding-proposal th,.coding-proposal td{padding:10px;border-bottom:1px solid #e2e8f0}.coding-proposal button{padding:9px 14px;border:1px solid #cbd5e1;border-radius:8px;background:#f8fafc;cursor:pointer;width:fit-content}.coding-proposal button:disabled{opacity:.5;cursor:wait}.coding-diff{white-space:pre;overflow:auto;max-height:420px;background:#111827;color:#e2e8f0;padding:16px;border-radius:8px;font-size:12px}.coding-note{color:#64748b;font-size:13px}.coding-error{color:#b42318}.coding-actions{display:flex;gap:10px}.coding-proposal summary{cursor:pointer}.coding-proposal code{overflow-wrap:anywhere}
.coding-diff code{background:transparent;color:inherit;padding:0;border-radius:0;overflow-wrap:normal;word-break:normal}
.coding-proposal{padding:18px 22px}.coding-proposal .panel-title{padding:0;flex-wrap:wrap}
.coding-evidence{display:grid;gap:12px}.coding-evidence blockquote{white-space:pre-wrap;margin:12px 0;padding:12px;background:#f8fafc;overflow-wrap:anywhere}
.coding-application,.coding-legacy{padding:14px 16px;border:1px solid #cbd5e1;border-radius:10px;background:#f8fafc;font-size:14px}.coding-application strong,.coding-legacy strong{display:block;margin-bottom:4px}.coding-review{display:grid;gap:14px;min-width:0}.coding-review h3,.coding-review h4{margin:0}.coding-change{border:1px solid #dbe3ee;border-radius:10px;padding:16px;min-width:0}.coding-change-heading{display:flex;gap:8px;flex-wrap:wrap;align-items:center;justify-content:space-between}.coding-check{border-radius:20px;padding:4px 10px;font-size:12px;background:#fff7ed;color:#9a3412;white-space:nowrap}.coding-check-passed{background:#ecfdf5;color:#166534}.coding-comparison{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin:12px 0 0}.coding-comparison>div{padding:12px;border-radius:8px;background:#f8fafc;min-width:0}.coding-comparison dt{font-size:13px;font-weight:700;color:#475569;margin-bottom:6px}.coding-comparison dd{margin:0;line-height:1.6;overflow-wrap:anywhere}.coding-test-evidence{font-size:12px;color:#64748b;margin-top:10px}.coding-test-evidence ul{padding-left:18px}.coding-remaining{background:#fffbeb;border:1px solid #fde68a;border-radius:10px;padding:16px;display:grid;gap:14px}.coding-remaining h4{font-size:14px;margin-bottom:4px}.coding-remaining p,.coding-scope li{font-size:14px;line-height:1.65}.coding-remaining article+article{border-top:1px solid #fde68a;padding-top:12px}.coding-scope ul{padding-left:20px;margin-bottom:0}.coding-model-explanation{border:1px solid #e2e8f0;border-radius:8px;padding:12px}.coding-model-explanation[open]{display:grid;gap:10px}.coding-model-explanation p,.coding-model-explanation li{font-size:14px;overflow-wrap:anywhere}
@media(max-width:600px){.coding-proposal{padding:16px}.coding-proposal th,.coding-proposal td{padding:8px}.coding-comparison{grid-template-columns:1fr}.coding-change{padding:12px}.coding-remaining{padding:12px}}
</style>
