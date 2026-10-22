<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()
const title = computed(() => String(route.meta.title ?? 'Trang đang xây dựng'))
const description = computed(() => String(route.meta.description ?? 'Nội dung sẽ được cập nhật trong task tiếp theo.'))
</script>

<template>
  <section class="placeholder-page">
    <p class="eyebrow">Mộc Store</p>
    <h1>{{ title }}</h1>
    <p>{{ description }}</p>
    <RouterLink class="button button--primary" to="/">Về trang chủ</RouterLink>
  </section>
</template>
