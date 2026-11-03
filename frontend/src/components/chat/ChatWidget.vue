<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import { confirmChatAction, sendChatMessage } from '../../services/chat'
import { clearPendingChatAction, pendingChatAction } from '../../stores/chat-action'
import type { ChatHistoryItem, ChatProduct, ChatProposedAction, ChatSource, ChatStatus } from '../../types/chat'
import ChatProductCard from './ChatProductCard.vue'

interface ChatMessage extends ChatHistoryItem {
  products?: ChatProduct[]
  sources?: ChatSource[]
  status?: ChatStatus
  proposedAction?: ChatProposedAction | null
  actionError?: string
  lookupToken?: string
  confirmationAttempt?: { clientMessageId: string; idempotencyKey: string }
}

const HISTORY_LIMIT = 6
const isOpen = ref(false)
const input = ref<HTMLTextAreaElement | null>(null)
const toggleButton = ref<HTMLButtonElement | null>(null)
const message = ref('')
const messages = ref<ChatMessage[]>([])
const loading = ref(false)
const confirming = ref(false)
const currentTime = ref(Date.now())
let clockTimer: ReturnType<typeof setInterval> | undefined
const errorMessage = ref('')
const canSend = computed(() => Boolean(message.value.trim()) && !loading.value)
const statusLabels: Record<ChatStatus, string> = {
  ok: 'Đã tìm thấy thông tin phù hợp',
  insufficient_data: 'Chưa đủ dữ liệu để tư vấn',
  out_of_scope: 'Ngoài phạm vi hỗ trợ sản phẩm',
  provider_unavailable: 'Dịch vụ tư vấn tạm thời không khả dụng',
}
const actionLabels: Record<ChatProposedAction['action'], string> = {
  cart_add: 'Thêm vào giỏ hàng',
  cart_update: 'Cập nhật giỏ hàng',
  cart_remove: 'Xóa khỏi giỏ hàng',
  order_create: 'Tạo đơn hàng (thanh toán mô phỏng nếu chọn online)',
  order_cancel: 'Hủy đơn hàng',
  refund_request: 'Yêu cầu hoàn tiền mô phỏng',
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
    const requestedAction = pendingChatAction.value
    const response = requestedAction
      ? await sendChatMessage(content, history, {
          actionContext: requestedAction.actionContext,
          lookupToken: requestedAction.lookupToken,
        })
      : await sendChatMessage(content, history)
    clearPendingChatAction()
    messages.value = keepBounded([
      ...messages.value,
      {
        role: 'assistant',
        content: response.answer,
        products: response.products,
        sources: response.sources.filter((source) => source.source_type === 'knowledge'),
        status: response.status,
        proposedAction: response.proposed_action,
        lookupToken: requestedAction?.lookupToken,
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

const proposalExpired = (proposal: ChatProposedAction) => {
  const expiresAt = new Date(proposal.expires_at).getTime()
  return !Number.isFinite(expiresAt) || expiresAt <= currentTime.value
}

const confirmationDisabled = (item: ChatMessage) => Boolean(
  item.proposedAction
  && proposalExpired(item.proposedAction)
  && !item.confirmationAttempt,
)

const cancelProposal = (item: ChatMessage) => {
  item.proposedAction = null
  item.actionError = 'Bạn đã hủy đề xuất. Không có thay đổi nào được thực hiện.'
}

const confirmProposal = async (item: ChatMessage) => {
  const proposal = item.proposedAction
  if (!proposal || confirming.value) return
  if (proposalExpired(proposal) && !item.confirmationAttempt) {
    item.actionError = 'Xác nhận đã hết hạn. Hãy gửi lại yêu cầu để lấy đề xuất mới.'
    return
  }

  confirming.value = true
  item.actionError = ''
  try {
    const attempt = item.confirmationAttempt ?? {
      clientMessageId: crypto.randomUUID(),
      idempotencyKey: `chat-action-${crypto.randomUUID()}`,
    }
    item.confirmationAttempt = attempt
    const response = item.lookupToken
      ? await confirmChatAction(
          proposal.confirmation_token,
          attempt.clientMessageId,
          attempt.idempotencyKey,
          item.lookupToken,
        )
      : await confirmChatAction(
          proposal.confirmation_token,
          attempt.clientMessageId,
          attempt.idempotencyKey,
        )
    item.proposedAction = null
    item.confirmationAttempt = undefined
    messages.value = keepBounded([
      ...messages.value,
      {
        role: 'assistant',
        content: response.answer,
        products: response.products,
        sources: response.sources.filter((source) => source.source_type === 'knowledge'),
        status: response.status,
        proposedAction: response.proposed_action,
      },
    ])
  } catch (error) {
    const code = (
      typeof error === 'object'
      && error !== null
      && 'payload' in error
      && typeof error.payload === 'object'
      && error.payload !== null
      && 'error' in error.payload
      && typeof error.payload.error === 'object'
      && error.payload.error !== null
      && 'code' in error.payload.error
    ) ? String(error.payload.error.code) : null
    const status = (
      typeof error === 'object'
      && error !== null
      && 'status' in error
      && typeof error.status === 'number'
    ) ? error.status : null
    const terminalCodes = new Set([
      'CHAT_ACTION_UNAVAILABLE',
      'CONFIRMATION_ALREADY_USED',
      'CONFIRMATION_EXPIRED',
      'CONFIRMATION_INVALID',
      'IDEMPOTENCY_KEY_REUSED',
      'CART_VERSION_CONFLICT',
      'ORDER_STATUS_NOT_CANCELLABLE',
      'OUT_OF_STOCK',
      'PRICE_CHANGED',
    ])
    const terminalClientError = status !== null
      && status >= 400
      && status < 500
      && status !== 408
      && status !== 429
    if ((code && terminalCodes.has(code)) || terminalClientError) {
      item.proposedAction = null
      item.confirmationAttempt = undefined
      item.actionError = 'Không thể xác nhận vì đề xuất đã dùng, hết hạn hoặc dữ liệu đã thay đổi. Hãy tải lại trạng thái và tạo đề xuất mới.'
    } else if (status === 429) {
      item.actionError = 'Đang có quá nhiều yêu cầu. Vui lòng chờ một lúc rồi thử lại với cùng mã yêu cầu.'
    } else {
      item.actionError = 'Chưa nhận được kết quả xác nhận. Bạn có thể thử lại an toàn với cùng mã yêu cầu.'
    }
  } finally {
    confirming.value = false
  }
}

const handleComposerKeydown = (event: KeyboardEvent) => {
  if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) {
    event.preventDefault()
    void submitMessage()
  }
}

const submitSuggestion = async (content: string) => {
  message.value = content
  await submitMessage()
}

onMounted(() => {
  document.addEventListener('keydown', handleEscape)
  clockTimer = setInterval(() => {
    currentTime.value = Date.now()
  }, 500)
})
onBeforeUnmount(() => {
  document.removeEventListener('keydown', handleEscape)
  if (clockTimer) clearInterval(clockTimer)
})
watch(pendingChatAction, async (request) => {
  if (!request) return
  message.value = request.prompt
  await open()
})
</script>

<template>
  <aside class="chat-widget" data-testid="chat-widget-position">
    <section
      v-if="isOpen"
      id="product-chat-panel"
      class="chat-widget__panel"
      role="dialog"
      aria-label="Trợ lý mua sắm"
    >
      <header class="chat-widget__header">
        <div>
          <strong>Trợ lý mua sắm</strong>
          <p>Hỏi về sản phẩm, màu, size, ngân sách hoặc chính sách đổi trả.</p>
        </div>
        <button type="button" aria-label="Đóng trợ lý mua sắm" @click="close">×</button>
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
          <div
            v-if="item.sources?.length"
            class="chat-widget__citations"
            data-testid="chat-citations"
          >
            <span>Nguồn:</span>
            <ul>
              <li v-for="source in item.sources" :key="source.source_id">{{ source.title }}</li>
            </ul>
          </div>
          <section
            v-if="item.proposedAction"
            class="chat-widget__proposal"
            data-testid="chat-proposed-action"
            aria-label="Xác nhận thao tác được đề xuất"
          >
            <strong>{{ actionLabels[item.proposedAction.action] }}</strong>
            <p>{{ item.proposedAction.summary }}</p>
            <p>Mã tài nguyên: <b>{{ item.proposedAction.resource_code }}</b></p>
            <p v-if="proposalExpired(item.proposedAction) && !item.confirmationAttempt" role="alert">
              Xác nhận đã hết hạn. Hãy gửi lại yêu cầu để lấy đề xuất mới.
            </p>
            <p v-else-if="proposalExpired(item.proposedAction)" role="status">
              Đề xuất ban đầu đã hết hạn; lần thử đang xử lý vẫn dùng lại cùng mã yêu cầu an toàn.
            </p>
            <div class="chat-widget__proposal-actions">
              <button
                type="button"
                data-testid="chat-action-confirm"
                :disabled="confirming || confirmationDisabled(item)"
                @click="confirmProposal(item)"
              >
                {{ confirming ? 'Đang xác nhận…' : 'Xác nhận' }}
              </button>
              <button
                type="button"
                data-testid="chat-action-cancel"
                :disabled="confirming"
                @click="cancelProposal(item)"
              >
                Hủy
              </button>
            </div>
          </section>
          <p v-if="item.actionError" class="chat-widget__error" role="alert">{{ item.actionError }}</p>
        </article>
        <p v-if="loading" class="chat-widget__loading" role="status">Đang tìm sản phẩm…</p>
        <p v-if="errorMessage" class="chat-widget__error" role="alert">{{ errorMessage }}</p>
      </div>
      <div v-else class="chat-widget__empty">
        <p>Xin chào! Tôi có thể giúp bạn tìm sản phẩm phù hợp.</p>
        <button
          type="button"
          class="chat-widget__suggestion"
          data-testid="chat-suggestion-return-policy"
          @click="submitSuggestion('Chính sách đổi trả như thế nào?')"
        >
          Chính sách đổi trả
        </button>
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
      :aria-label="isOpen ? 'Đóng trợ lý mua sắm' : 'Mở trợ lý mua sắm'"
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
  top: max(10.5rem, env(safe-area-inset-top));
  right: max(var(--space-4), env(safe-area-inset-right));
  bottom: auto;
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
  max-height: min(36rem, calc(100dvh - 15rem));
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

.chat-widget__citations {
  margin-top: var(--space-3);
  color: var(--color-ink-muted);
  font-size: var(--font-size-sm);
}

.chat-widget__citations ul {
  margin: var(--space-1) 0 0;
  padding-left: var(--space-4);
}

.chat-widget__suggestion {
  margin-top: var(--space-3);
  padding: var(--space-2) var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-pill);
  background: var(--color-surface);
  color: var(--color-ink);
  font-weight: var(--font-weight-bold);
}

.chat-widget__status {
  margin-top: var(--space-2) !important;
  color: var(--color-ink-muted);
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-bold);
}

.chat-widget__proposal {
  display: grid;
  gap: var(--space-2);
  margin-top: var(--space-3);
  padding: var(--space-3);
  border: 1px solid var(--color-accent);
  border-radius: var(--radius-md);
  background: var(--color-surface);
}

.chat-widget__proposal-actions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
}

.chat-widget__proposal-actions button {
  min-height: 2.75rem;
  padding-inline: var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-pill);
  background: var(--color-surface-soft);
  color: var(--color-ink);
  font-weight: var(--font-weight-bold);
}

.chat-widget__proposal-actions button:first-child {
  background: var(--color-accent);
  color: var(--color-surface);
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
    top: auto;
    right: var(--space-6);
    bottom: var(--space-6);
  }

  .chat-widget__panel {
    max-height: min(36rem, calc(100dvh - 7rem));
  }
}

@media (max-height: 30rem) {
  .chat-widget {
    top: var(--space-2);
    bottom: var(--space-2);
  }

  .chat-widget__panel {
    max-height: calc(100dvh - 4.5rem);
  }
}
</style>
