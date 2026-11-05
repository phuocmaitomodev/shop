<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { accountErrorMessage, login } from '../services/auth-account'

const router = useRouter()
const form = reactive({ email: '', password: '' })
const submitting = ref(false)
const errorMessage = ref('')

const submit = async () => {
  if (submitting.value) return
  submitting.value = true
  errorMessage.value = ''
  try {
    const profile = await login({ email: form.email, password: form.password })
    if (profile.role === 'customer') {
      await router.push({ name: 'account' })
      return
    }
    errorMessage.value = 'Tài khoản này không thuộc khu vực khách hàng.'
  } catch (error) {
    errorMessage.value = accountErrorMessage(error)
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <section class="commerce-page commerce-page--narrow auth-page" aria-labelledby="login-title">
    <header>
      <p class="eyebrow">Mộc Store · Tài khoản</p>
      <h1 id="login-title">Đăng nhập</h1>
      <p class="auth-page__intro">Dùng email và mật khẩu để truy cập tài khoản khách hàng.</p>
    </header>

    <form class="commerce-form auth-card" @submit.prevent="submit">
      <label for="login-email">
        Email
        <input
          id="login-email"
          v-model.trim="form.email"
          type="email"
          name="email"
          autocomplete="email"
          required
          maxlength="320"
        >
      </label>
      <label for="login-password">
        Mật khẩu
        <input
          id="login-password"
          v-model="form.password"
          type="password"
          name="password"
          autocomplete="current-password"
          required
          maxlength="128"
        >
      </label>
      <p v-if="errorMessage" class="commerce-alert" role="alert">{{ errorMessage }}</p>
      <button type="submit" :disabled="submitting">
        {{ submitting ? 'Đang đăng nhập…' : 'Đăng nhập' }}
      </button>
    </form>
  </section>
</template>
