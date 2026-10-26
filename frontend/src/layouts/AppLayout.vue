<script setup lang="ts">
import ChatWidget from '../components/chat/ChatWidget.vue'
import SiteFooter from '../components/SiteFooter.vue'
import SiteHeader from '../components/SiteHeader.vue'
</script>

<template>
  <div class="app-shell">
    <a class="skip-link" href="#main-content">Bỏ qua đến nội dung chính</a>
    <SiteHeader />
    <main id="main-content" class="main-content">
      <RouterView />
    </main>
    <SiteFooter />
    <ChatWidget />
  </div>
</template>
