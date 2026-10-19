<script setup lang="ts">
import { ref } from "vue";
import { useRouter } from "vue-router";
import { ArrowRight, LockKeyhole } from "lucide-vue-next";
import { useSession } from "../stores/session";
const s = useSession(),
  router = useRouter();
const username = ref(""),
  password = ref(""),
  error = ref(""),
  busy = ref(false);
async function submit() {
  busy.value = true;
  error.value = "";
  try {
    await s.login(username.value, password.value);
    router.push("/");
  } catch (e: any) {
    error.value = e.message;
  } finally {
    busy.value = false;
    password.value = "";
  }
}
</script>
<template>
  <main class="login">
    <section class="login-story">
      <img
        src="/csi.png"
        alt="CSI — Cyber Security Inspector"
        class="login-brand"
      />
      <div class="eyebrow">CONTINUOUS SECURITY. VERIFIED EVIDENCE.</div>
      <h1>코드가 바뀌는 순간,<br />보안의 기준을 확인하세요.</h1>
      <p>
        코드와 정책 사이의 간극을 발견하고,<br />검증 가능한 근거로 다음 결정을
        내립니다.
      </p>
      <div class="pipeline">
        <span>CODE</span><i /><span>POLICY</span><i /><span>INSIGHT</span>
      </div>
      <small>CSI / SECURITY OPERATIONS PLATFORM</small>
    </section>
    <section class="login-form">
      <form @submit.prevent="submit">
        <img src="/logo.png" class="shield" alt="CSI 보안 심벌" />
        <h2>워크스페이스 로그인</h2>
        <p>보안 진단 콘솔에 접속합니다.</p>
        <label
          >계정<input
            v-model="username"
            required
            maxlength="100"
            autocomplete="username"
            placeholder="보안 담당자 계정" /></label
        ><label
          >비밀번호<input
            v-model="password"
            required
            minlength="8"
            type="password"
            autocomplete="current-password"
            placeholder="비밀번호를 입력하세요"
        /></label>
        <div v-if="error" role="alert" class="error">{{ error }}</div>
        <button class="primary" :disabled="busy">
          {{ busy ? "인증 중…" : "로그인" }}<ArrowRight :size="17" />
        </button>
        <p class="secure-note">
          <LockKeyhole :size="14" /> 승인된 사용자만 접근할 수 있습니다.
        </p>
      </form>
    </section>
  </main>
</template>
