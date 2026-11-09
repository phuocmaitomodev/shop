<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import {
  accountErrorMessage,
  getAccountProfile,
  isAuthenticationRequired,
  logout,
  updateAccountProfile,
} from '../services/auth-account'
import type { AccountProfile } from '../types/auth-account'

const router = useRouter()
const profile = ref<AccountProfile | null>(null)
const loading = ref(true)
const saving = ref(false)
const loggingOut = ref(false)
const unauthenticated = ref(false)
const errorMessage = ref('')
const successMessage = ref('')
const form = reactive({ full_name: '', phone: '' })

const applyProfile = (value: AccountProfile) => {
  profile.value = value
  form.full_name = value.full_name
  form.phone = value.phone ?? ''
}

const loadProfile = async () => {
  loading.value = true
  unauthenticated.value = false
  errorMessage.value = ''
  successMessage.value = ''
  try {
    applyProfile(await getAccountProfile())
  } catch (error) {
    profile.value = null
    if (isAuthenticationRequired(error)) {
      unauthenticated.value = true
    } else {
      errorMessage.value = accountErrorMessage(error)
    }
  } finally {
    loading.value = false
  }
}

const saveProfile = async () => {
  if (saving.value) return
  saving.value = true
  errorMessage.value = ''
  successMessage.value = ''
  try {
    applyProfile(await updateAccountProfile({
      full_name: form.full_name,
      phone: form.phone.trim() || null,
    }))
    successMessage.value = 'Đã lưu thay đổi hồ sơ.'
  } catch (error) {
    errorMessage.value = accountErrorMessage(error)
  } finally {
    saving.value = false
  }
}

const signOut = async () => {
  if (loggingOut.value) return
  loggingOut.value = true
  errorMessage.value = ''
  successMessage.value = ''
  try {
    await logout()
    profile.value = null
    await router.push({ name: 'login' })
  } catch (error) {
    errorMessage.value = accountErrorMessage(error)
  } finally {
    loggingOut.value = false
  }
}

onMounted(loadProfile)
</script>

<template>
  <section class="commerce-page commerce-page--narrow auth-page" aria-labelledby="account-title">
    <header>
      <p class="eyebrow">Mộc Store · Tài khoản</p>
      <h1 id="account-title">Hồ sơ của tôi</h1>
      <p class="auth-page__intro">Thông tin được tải trực tiếp từ tài khoản đang đăng nhập.</p>
    </header>

    <p v-if="loading" role="status">Đang tải hồ sơ…</p>

    <div v-else-if="unauthenticated" class="commerce-empty">
      <h2>Bạn chưa đăng nhập</h2>
      <p>Đăng nhập để xem và cập nhật hồ sơ khách hàng.</p>
      <RouterLink data-testid="login-cta" class="button button--primary" to="/dang-nhap">
        Đi đến đăng nhập
      </RouterLink>
    </div>

    <div v-else-if="!profile" class="commerce-state commerce-state--error">
      <p role="alert">{{ errorMessage }}</p>
      <button data-testid="profile-retry" type="button" @click="loadProfile">Thử tải lại</button>
    </div>

    <form v-else class="commerce-form auth-card" @submit.prevent="saveProfile">
      <label for="account-email">
        Email
        <input id="account-email" :value="profile.email" type="email" readonly autocomplete="email">
        <span class="auth-field-help">Email đăng nhập không thể thay đổi tại đây.</span>
      </label>
      <label for="account-full-name">
        Họ và tên
        <input
          id="account-full-name"
          v-model="form.full_name"
          type="text"
          autocomplete="name"
          required
          maxlength="200"
        >
      </label>
      <label for="account-phone">
        Số điện thoại
        <input
          id="account-phone"
          v-model="form.phone"
          type="tel"
          autocomplete="tel"
          inputmode="tel"
          maxlength="32"
        >
      </label>

      <p v-if="successMessage" class="commerce-success" role="status">{{ successMessage }}</p>
      <p v-if="errorMessage" class="commerce-alert" role="alert">{{ errorMessage }}</p>

      <div class="commerce-actions">
        <button type="submit" :disabled="saving || loggingOut">
          {{ saving ? 'Đang lưu…' : 'Lưu thay đổi' }}
        </button>
        <button
          data-testid="logout"
          class="auth-button--secondary"
          type="button"
          :disabled="saving || loggingOut"
          @click="signOut"
        >
          {{ loggingOut ? 'Đang đăng xuất…' : 'Đăng xuất' }}
        </button>
      </div>
    </form>
  </section>
</template>
