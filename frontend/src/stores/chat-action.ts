import { ref } from 'vue'

import type { ChatActionContext } from '../types/chat'

export interface PendingChatAction {
  actionContext: ChatActionContext
  lookupToken?: string
  prompt: string
}

export const pendingChatAction = ref<PendingChatAction | null>(null)

export const requestChatAction = (request: PendingChatAction) => {
  pendingChatAction.value = request
}

export const clearPendingChatAction = () => {
  pendingChatAction.value = null
}
