<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'

import { sendChatMessage } from '../../services/chat'
import type { ChatHistoryItem, ChatProduct, ChatStatus } from '../../types/chat'
import ChatProductCard from './ChatProductCard.vue'

interface ChatMessage extends ChatHistoryItem {
  products?: ChatProduct[]
  status?: ChatStatus
}

const HISTORY_LIMIT = 6
const isOpen = ref(false)
const input = ref<HTMLTextAreaElement | null>(null)
const toggleButton = ref<HTMLButtonElement | null>(null)
const message = ref('')
const messages = ref<ChatMessage[]>([])
const loading = ref(false)
const errorMessage = ref('')
const canSend = computed(() => Boolean(message.value.trim()) && !loading.value)
const statusLabels: Record<ChatStatus, string> = {
  ok: 'Đã tìm thấy thông tin phù hợp',
  insufficient_data: 'Chưa đủ dữ liệu để tư vấn',
  out_of_scope: 'Ngoài phạm vi hỗ trợ sản phẩm',
  provider_unavailable: 'Dịch vụ tư vấn tạm thời không khả dụng',
}

const open = async () => {
  isOpen.value = true
  await nextTick()
  input.value?.focus()
}

const close = async () => {
  isOpen.value = false
  await nextTick()
  toggleButton.value?.focus()
}

const toggle = () => {
  if (isOpen.value) void close()
  else void open()
}

const handleEscape = (event: KeyboardEvent) => {
  if (event.key === 'Escape' && isOpen.value) void close()
}

const keepBounded = (items: ChatMessage[]) => items.slice(-HISTORY_LIMIT)

const submitMessage = async () => {
  const content = message.value.trim()
  if (!content || loading.value) return

  const history = messages.value.map(({ role, content: previousContent }) => ({
    role,
    content: previousContent,
  }))
  messages.value = keepBounded([...messages.value, { role: 'user', content }])
  message.value = ''
  errorMessage.value = ''
  loading.value = true

  try {
    const response = await sendChatMessage(content, history)
    messages.value = keepBounded([
      ...messages.value,
      {
        role: 'assistant',
        content: response.answer,
        products: response.products,
        status: response.status,
      },
    ])
  } catch {
    errorMessage.value = 'Không thể gửi câu hỏi lúc này. Vui lòng thử lại.'
  } finally {
    loading.value = false
    await nextTick()
    input.value?.focus()
  }
}

const handleComposerKeydown = (event: KeyboardEvent) => {
  if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) {
    event.preventDefault()
    void submitMessage()
  }
}

onMounted(() => document.addEventListener('keydown', handleEscape))
onBeforeUnmount(() => document.removeEventListener('keydown', handleEscape))
</script>

<template>
  <aside class="chat-widget" data-testid="chat-widget-position">
    <section
      v-if="isOpen"
      id="product-chat-panel"
      class="chat-widget__panel"
      role="dialog"
      aria-label="Trợ lý sản phẩm"
    >
      <header class="chat-widget__header">
        <div>
          <strong>Trợ lý sản phẩm</strong>
          <p>Hỏi về sản phẩm, màu, size và ngân sách.</p>
        </div>
        <button type="button" aria-label="Đóng trợ lý sản phẩm" @click="close">×</button>
      </header>
      <div
        v-if="messages.length"
        class="chat-widget__messages"
        data-testid="chat-messages"
        aria-live="polite"
      >
        <article
          v-for="(item, index) in messages"
          :key="`${item.role}-${index}`"
          class="chat-widget__message"
          :class="`chat-widget__message--${item.role}`"
        >
          <span class="sr-only">{{ item.role === 'user' ? 'Bạn' : 'Trợ lý' }}:</span>
          <p>{{ item.content }}</p>
          <p
            v-if="item.status"
            class="chat-widget__status"
            data-testid="chat-status"
          >
            {{ statusLabels[item.status] }}
          </p>
          <div v-if="item.products?.length" class="chat-widget__products">
            <ChatProductCard
              v-for="product in item.products"
              :key="product.id"
              :product="product"
            />
          </div>
        </article>
        <p v-if="loading" class="chat-widget__loading" role="status">Đang tìm sản phẩm…</p>
        <p v-if="errorMessage" class="chat-widget__error" role="alert">{{ errorMessage }}</p>
      </div>
      <div v-else class="chat-widget__empty">
        <p>Xin chào! Tôi có thể giúp bạn tìm sản phẩm phù hợp.</p>
      </div>
      <form class="chat-widget__composer" @submit.prevent="submitMessage">
        <label class="sr-only" for="chat-message">Câu hỏi về sản phẩm</label>
        <textarea
          id="chat-message"
          ref="input"
          v-model="message"
          rows="2"
          maxlength="1000"
          placeholder="Ví dụ: Tìm áo thun đen size M…"
          :disabled="loading"
          @keydown="handleComposerKeydown"
        />
        <button type="submit" :disabled="!canSend">Gửi</button>
      </form>
    </section>
    <button
      ref="toggleButton"
      class="chat-widget__toggle"
      type="button"
      data-testid="chat-toggle"
      :aria-expanded="isOpen"
      aria-controls="product-chat-panel"
      :aria-label="isOpen ? 'Đóng trợ lý sản phẩm' : 'Mở trợ lý sản phẩm'"
      @click="toggle"
    >
      <span aria-hidden="true">✦</span>
      <span>{{ isOpen ? 'Đóng' : 'Hỏi sản phẩm' }}</span>
    </button>
  </aside>
</template>

<style scoped>
.chat-widget {
  position: fixed;
  right: max(var(--space-4), env(safe-area-inset-right));
  bottom: max(var(--space-4), env(safe-area-inset-bottom));
  z-index: 30;
  display: grid;
  justify-items: end;
  gap: var(--space-3);
  pointer-events: none;
}

.chat-widget button,
.chat-widget__panel {
  pointer-events: auto;
}

.chat-widget__toggle,
.chat-widget__header button,
.chat-widget__composer button {
  min-width: 2.75rem;
  min-height: 2.75rem;
  border: 0;
  cursor: pointer;
}

.chat-widget__toggle {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-3) var(--space-4);
  border-radius: var(--radius-pill);
  background: var(--color-accent);
  box-shadow: 0 0.75rem 2rem rgba(24, 32, 28, 0.24);
  color: var(--color-surface);
  font-weight: var(--font-weight-bold);
}

.chat-widget__panel {
  display: grid;
  width: min(24rem, calc(100vw - 2rem));
  max-height: min(36rem, calc(100dvh - 7rem));
  overflow: hidden;
  grid-template-rows: auto minmax(0, 1fr) auto;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  background: var(--color-surface);
  box-shadow: 0 1rem 3rem rgba(24, 32, 28, 0.22);
}

.chat-widget__header {
  display: flex;
  align-items: start;
  justify-content: space-between;
  gap: var(--space-3);
  padding: var(--space-4);
  background: var(--color-ink);
  color: var(--color-surface);
}

.chat-widget__header p {
  margin: var(--space-1) 0 0;
  color: #dce1de;
  font-size: var(--font-size-sm);
}

.chat-widget__header button {
  border-radius: 50%;
  background: transparent;
  color: inherit;
  font-size: 1.5rem;
}

.chat-widget__empty,
.chat-widget__messages {
  overflow-y: auto;
  padding: var(--space-4);
  color: var(--color-ink-muted);
}

.chat-widget__messages {
  display: grid;
  align-content: start;
  gap: var(--space-3);
}

.chat-widget__message {
  max-width: 92%;
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-md);
  background: var(--color-surface-soft);
  color: var(--color-ink);
}

.chat-widget__message--user {
  justify-self: end;
  background: var(--color-ink);
  color: var(--color-surface);
}

.chat-widget__message p,
.chat-widget__loading,
.chat-widget__error {
  margin: 0;
  overflow-wrap: anywhere;
  white-space: pre-wrap;
}

.chat-widget__products {
  display: grid;
  gap: var(--space-2);
  margin-top: var(--space-3);
}

.chat-widget__status {
  margin-top: var(--space-2) !important;
  color: var(--color-ink-muted);
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-bold);
}

.chat-widget__loading {
  font-size: var(--font-size-sm);
}

.chat-widget__error {
  color: var(--color-accent-strong);
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-bold);
}

.chat-widget__composer {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: var(--space-2);
  padding: var(--space-3);
  border-top: 1px solid var(--color-border);
}

.chat-widget__composer textarea {
  min-width: 0;
  resize: none;
  padding: var(--space-2) var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
}

.chat-widget__composer button {
  align-self: stretch;
  padding-inline: var(--space-4);
  border-radius: var(--radius-pill);
  background: var(--color-accent);
  color: var(--color-surface);
  font-weight: var(--font-weight-bold);
}

.chat-widget__composer button:disabled {
  cursor: not-allowed;
  opacity: 0.55;
}

@media (min-width: 48rem) {
  .chat-widget {
    right: var(--space-6);
    bottom: var(--space-6);
  }
}
</style>
