<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { RouterLink } from 'vue-router';
import Badge from './Badge.vue';
const props = defineProps<{ changes: any; findings: any[]; scanStatus?: string }>();
const selected = ref('');
const files = computed(() => props.changes?.files || []);
watch(files, () => { if (!files.value.some((f: any) => f.changeId === selected.value)) selected.value = files.value[0]?.changeId || ''; }, { immediate: true });
const file = computed(() => files.value.find((f: any) => f.changeId === selected.value));
const current = computed(() => (props.findings || []).filter(f => f.filePath === file.value?.filePath));
const old = computed(() => (props.changes?.baselineFindings || []).filter((f: any) => f.filePath === file.value?.filePath));
const removed = computed(() => old.value.filter((f: any) => !(props.findings || []).some(n => n.fingerprint === f.fingerprint)));
const review = computed(() => props.changes?.review?.files?.find((r: any) => r.changeId === selected.value));
const stateLabels: Record<string, string> = { NOT_PROVIDED: '이 검사는 코드 변경 근거를 수집하지 않았습니다. 새 스캐너로 기준·현재 커밋을 지정해 검사하세요.', NO_BASE: '기준 커밋이 없는 검사입니다. 최초 Push 또는 기준 정보가 없는 실행은 변경 비교를 만들지 않습니다.', BASE_UNAVAILABLE: '기준 커밋을 저장소에서 찾지 못했습니다. 현재 검사는 유효하지만 변경 비교는 제공할 수 없습니다.' };
const kindLabels: Record<string, string> = { ADDED: '파일 추가', DELETED: '파일 삭제', MODIFIED: '파일 수정' };
function summary(fact: any) {
  const labels: Record<string, string> = { FIELD_ADDED: '필드 선언 추가', FIELD_REMOVED: '필드 선언 삭제', FUNCTION_ADDED: '함수 선언 추가', FUNCTION_REMOVED: '함수 선언 삭제' };
  const symbols: Record<string, string> = { 'Signup.phone_number': '회원가입 전화번호 입력', 'Signup.name': '회원가입 이름 입력', 'User.name': '사용자 이름 모델', 'CsiSignupProfile.phone_number': '실습 프로필 전화번호 모델' };
  return `${symbols[fact.symbol] || fact.symbol} · ${labels[fact.kind] || fact.kind} (${fact.line}행)`;
}
function riskState(f: any) { return old.value.some((b: any) => b.fingerprint === f.fingerprint) ? '기존 후보 유지' : '신규 정적 후보'; }
</script>
<template>
  <section class="panel change-review" aria-label="코드 변경 리뷰">
    <div class="panel-title"><h2>코드 변경 리뷰</h2><span>Git 기준 커밋과 현재 커밋 비교</span></div>
    <p v-if="changes?.status !== 'AVAILABLE'" class="change-note">{{ stateLabels[changes?.status || 'NOT_PROVIDED'] }}</p>
    <template v-else>
      <div class="change-meta"><span>수정 전 <code>{{ changes.baseSha }}</code></span><span>수정 후 <code>{{ changes.headSha }}</code></span></div>
      <p class="change-note">이전 검사 건수 비교와 기준이 다릅니다. Java/Python 소스의 실제 변경 구간을 표시하며 문자열·주석·긴 숫자 값은 마스킹합니다. 런타임 실행 로그는 포함하지 않습니다.</p>
      <p v-if="changes.truncated" role="status" class="change-note">변경 범위가 한도를 넘어 일부만 표시됩니다. 전체 {{ changes.totalChangedFiles }}개 중 {{ files.length }}개 파일 · 파일당 최대 100행.</p>
      <p v-if="!files.length" class="change-note">지원하는 Java/Python 소스에서 변경된 파일이 없습니다. 다른 언어·설정 파일의 변경은 이 비교 범위 밖입니다.</p>
      <template v-else>
        <label class="change-selector">변경 파일<select v-model="selected" aria-label="변경 파일"><option v-for="f in files" :key="f.changeId" :value="f.changeId">{{ kindLabels[f.changeType] }} · {{ f.filePath }}</option></select></label>
        <template v-if="file">
          <div class="change-body">
            <h3>변경 요약 <small>정적 선언 비교</small></h3>
            <p>{{ kindLabels[file.changeType] }} · 추가 {{ file.addedLines }}행 / 삭제 {{ file.removedLines }}행</p>
            <ul v-if="file.facts.length"><li v-for="fact in file.facts" :key="fact.id">{{ summary(fact) }}</li></ul>
            <p v-else>소스 내용이 변경됐습니다. 지원하는 선언 패턴에서 기능 추가·삭제를 식별하지 못했으므로 목적이나 동작을 추정하지 않습니다.</p>
            <small>선언 변화로 확인한 기능 후보입니다. 함수 이름만으로 실제 업무 목적이나 동작 완료를 확정하지 않습니다.</small>
          </div>
          <div class="diff-scroll" tabindex="0" aria-label="수정 전후 코드 비교">
            <table class="source-diff"><colgroup><col style="width:48px"><col><col style="width:48px"><col></colgroup><thead><tr><th colspan="2">수정 전</th><th colspan="2">수정 후</th></tr></thead><tbody>
              <tr v-for="(row, i) in file.rows" :key="i" :class="row.kind.toLowerCase()">
                <td class="line-number">{{ row.oldLine ?? '' }}</td><td class="diff-before"><pre>{{ row.before ?? '' }}</pre></td>
                <td class="line-number">{{ row.newLine ?? '' }}</td><td class="diff-after"><pre>{{ row.after ?? '' }}</pre></td>
              </tr>
            </tbody></table>
          </div>
          <p v-if="file.truncated" class="change-note">이 파일의 행·줄 길이·요약 일부가 제한되었습니다. 생략한 구간까지 검토했다고 해석하지 마세요.</p>
          <div class="change-body">
            <h3>변경 단위 보안 리뷰</h3>
            <p v-if="!review">{{ scanStatus === 'FAILED' ? 'Agent 분석이 실패했습니다. diff는 정적 근거이며 AI 변경 리뷰는 완료되지 않았습니다. 실행 로그를 확인하세요.' : 'Agent의 변경 근거 연결 결과를 기다리는 중입니다.' }}</p>
            <p>신규 {{ current.filter(f => riskState(f) === '신규 정적 후보').length }} · 유지 {{ current.filter(f => riskState(f) === '기존 후보 유지').length }} · 미탐지 {{ removed.length }}</p>
            <p class="change-note">같은 파일의 후보를 연결합니다. 변경 라인과의 연관성은 개별 근거를 확인하세요. 신규 탐지가 변경의 인과관계를 증명하거나 미탐지가 수정 완료를 보장하지 않습니다.</p>
            <article v-for="f in current" :key="f.id" class="change-risk">
              <div><Badge :value="f.severity" /> <strong>{{ riskState(f) }} · {{ f.ruleId }} · {{ f.title }}</strong></div>
              <p v-if="f.analysis?.changeContext">{{ f.analysis.changeContext.relation === 'CHANGED_LINES' ? '변경 라인과 탐지 위치가 겹칩니다.' : '같은 파일의 후보이며 제공된 변경 라인과 겹침은 확인되지 않았습니다.' }}</p>
              <p>{{ f.analysis?.red || '개별 후보 분석 대기 중' }}</p>
              <p>{{ f.analysis?.blue }}</p>
              <p v-if="f.analysis?.remediation"><strong>개선 권고:</strong> {{ f.analysis.remediation }}</p>
              <small>분석 모드: {{ f.analysis?.mode || '대기' }} · {{ f.evidenceStatus }}</small>
              <RouterLink :to="'/findings/' + f.id" class="text-link">코드 위치·사실·정책 인용 확인 →</RouterLink>
            </article>
            <article v-for="f in removed" :key="f.fingerprint" class="change-risk">
              <strong>미탐지 · {{ f.ruleId }} · {{ f.title }}</strong><p>기준 {{ f.startLine }}행의 정적 후보가 현재 검사에서 탐지되지 않았습니다. 실행 검증이나 조치 완료 판정은 수행하지 않았습니다.</p>
            </article>
            <p v-if="!current.length && !removed.length">이 변경 파일과 연결된 정적 보안 후보가 없습니다. 검사 범위 밖의 위험이나 기능의 안전성을 보증하지 않습니다.</p>
            <details v-if="removed.length && changes.review?.references?.length"><summary>미탐지 후보 검토에 사용한 정책 자료</summary><p v-for="r in changes.review.references" :key="r.chunkId">{{ r.documentId }} · {{ r.sectionId }} · {{ r.pageNumber }}쪽 · {{ r.sectionTitle }}</p></details>
          </div>
        </template>
      </template>
    </template>
  </section>
</template>
<style scoped>
.change-review{margin:20px 0}.change-meta{padding:0 24px;display:grid;gap:8px;font-size:13px}.change-meta code{overflow-wrap:anywhere}.change-note{padding:0 24px;color:var(--ink-2);font-size:13px;line-height:1.8}.change-selector{padding:12px 24px;display:grid;gap:8px}.change-selector select{width:100%;min-width:0}.change-body{padding:18px 24px}.change-body h3{font-size:15px;margin:0 0 12px}.change-body h3 small{font-size:11px;color:var(--ink-2);font-weight:400}.change-body p,.change-body li{font-size:13px;line-height:1.8;overflow-wrap:anywhere}.change-body .change-note{padding:0}.change-body ul{padding-left:20px;list-style:disc}.change-body small{display:block;color:var(--ink-2);line-height:1.7}.diff-scroll{overflow:auto;max-height:560px;border-block:1px solid var(--line)}.source-diff{min-width:800px;table-layout:fixed;width:100%;border-collapse:collapse}.source-diff th{text-align:left}.source-diff td{vertical-align:top;border-bottom:1px solid var(--line);padding:5px 8px}.source-diff .line-number{width:48px;color:var(--ink-2);font:11px monospace;text-align:right}.source-diff pre{font:12px/1.7 monospace;white-space:pre-wrap;overflow-wrap:anywhere;margin:0;background:none;padding:0;border:none;min-height:20px}.source-diff .modified .diff-before,.source-diff .deleted .diff-before{background:#fff0f1}.source-diff .modified .diff-after,.source-diff .added .diff-after{background:#eaf7ee}.change-risk{border-top:1px solid var(--line);padding:16px 0}.change-risk strong{font-size:13px}.change-risk .text-link{display:inline-block;margin-top:8px}@media(max-width:600px){.change-body,.change-meta,.change-selector{padding:12px 16px}.change-note{padding:0 16px}}
</style>
