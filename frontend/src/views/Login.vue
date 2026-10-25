<script setup lang="ts">
import { computed, ref } from "vue";
import { useRouter } from "vue-router";
import { LockKeyhole } from "lucide-vue-next";
import { useSession } from "../stores/session";
import ShieldScene from "../components/ShieldScene.vue";
// public/brand/ 워드마크가 없으면 기존 텍스트 제목을 보여 줍니다.
const BRAND = "/brand/";
const logoOk = ref(true);
const s = useSession(),
  router = useRouter();
const username = ref(""),
  password = ref(""),
  error = ref(""),
  busy = ref(false),
  done = ref(false);
// 입력이 채워질수록 자물쇠 걸쇠가 내려오고, 로그인에 성공하면 잠깁니다.
const progress = computed(
  () =>
    (username.value ? 0.35 : 0) +
    Math.min(password.value.length / 8, 1) * 0.65,
);
const lockState = computed(() =>
  done.value
    ? "locked"
    : busy.value
      ? "scanning"
      : error.value && !password.value
        ? "error"
        : "idle",
);
async function submit() {
  busy.value = true;
  error.value = "";
  try {
    await s.login(username.value, password.value);
    done.value = true;
    await new Promise((r) => setTimeout(r, 750));
    router.push("/projects");
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
      <h1 v-if="logoOk" class="wordmark-logo">
        <img
          :src="BRAND + 'csi-wordmark-full.png'"
          alt="CSI Context-aware Security Inspector"
          @error="logoOk = false"
        />
      </h1>
      <template v-else>
        <h1 class="wordmark">CSI</h1>
        <p class="wordmark-sub">
          Context-aware Security <span>Inspector</span>
        </p>
      </template>
      <p class="team">5조 : 노은서, 박지훈, 윤명진, 이기현, 장하은, 최현우</p>
      <p class="lede">
        코드가 바뀔 때마다 사내 개인정보 보호 정책을 근거로 위험을 찾고,<br />
        정적 분석 증거와 정책 조항을 함께 보여주는 보안 진단 콘솔입니다.
      </p>
      <div class="story-rule">
        <span>SKALA 4기 캡스톤</span><span>로컬 데모 환경</span>
      </div>
    </section>
    <section class="login-panel">
      <ShieldScene class="login-shield" :progress="progress" :state="lockState" />
      <form @submit.prevent="submit">
        <h2>워크스페이스 로그인</h2>
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
            placeholder="8자 이상"
        /></label>
        <div v-if="error" role="alert" class="error">{{ error }}</div>
        <button class="primary" :disabled="busy || done">
          {{ done ? "잠금 완료" : busy ? "인증 중…" : "로그인" }}
        </button>
        <p class="secure-note">
          <LockKeyhole :size="14" />승인된 사용자만 접근할 수 있습니다.
        </p>
      </form>
    </section>
  </main>
</template>

<style scoped>
.login {
  background:
    radial-gradient(65% 55% at 8% 0%, rgb(104 86 240 / 0.45), transparent 72%),
    radial-gradient(55% 65% at 100% 25%, rgb(63 94 232 / 0.3), transparent 72%),
    radial-gradient(75% 55% at 45% 100%, rgb(124 90 236 / 0.3), transparent 72%),
    #0c1738;
}
.login::before {
  opacity: 0.2;
}
.wordmark-logo img {
  filter: brightness(0) invert(1);
}
.wordmark,
.wordmark-sub,
.wordmark-sub span {
  color: #f3f5ff;
}
.team {
  color: #c7cff2;
}
.lede,
.story-rule {
  color: #b7c2e6;
}
.story-rule,
.story-rule span + span {
  border-color: rgb(255 255 255 / 0.18);
}
.login-panel form {
  box-shadow: 0 20px 50px rgb(5 10 35 / 0.3);
}
</style>
