<script setup lang="ts">
import { computed, ref, watch } from 'vue'

const props = withDefaults(defineProps<{
  src: string | null
  alt: string
  eager?: boolean
}>(), {
  eager: false,
})

const failed = ref(false)
watch(() => props.src, () => {
  failed.value = false
})

const imageSource = computed(() => {
  const source = props.src?.trim()
  if (!source || !source.startsWith('/')) return source

  try {
    return new URL(source, import.meta.env.VITE_API_BASE_URL).toString()
  } catch {
    return source
  }
})
const hasImage = computed(() => Boolean(imageSource.value) && !failed.value)
</script>

<template>
  <div class="product-image">
    <img
      v-if="hasImage"
      :src="imageSource"
      :alt="alt"
      :loading="eager ? 'eager' : 'lazy'"
      @error="failed = true"
    >
    <div
      v-else
      class="product-image__placeholder"
      data-testid="product-image-placeholder"
      role="img"
      :aria-label="`Chưa có ảnh cho ${alt}`"
    >
      <span aria-hidden="true">◇</span>
      <span>Chưa có ảnh</span>
    </div>
  </div>
</template>

<style scoped>
.product-image {
  width: 100%;
  height: 100%;
  min-height: 10rem;
  overflow: hidden;
  background: var(--color-surface-soft);
}

.product-image img {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.product-image__placeholder {
  display: grid;
  width: 100%;
  height: 100%;
  min-height: inherit;
  place-content: center;
  justify-items: center;
  gap: var(--space-2);
  color: var(--color-ink-muted);
  font-size: var(--font-size-sm);
}

.product-image__placeholder span:first-child {
  font-size: 2rem;
}
</style>
