import type { ApiSuccess } from '../types/api'
import type { ChatActionContext, ChatHistoryItem, ChatResponse } from '../types/chat'
import { apiClient } from './api-client'

interface SendChatOptions {
  actionContext?: ChatActionContext
  lookupToken?: string
}

export const sendChatMessage = async (
  message: string,
  history: ChatHistoryItem[] = [],
  options: SendChatOptions = {},
): Promise<ChatResponse> => {
  const response = await apiClient<ApiSuccess<ChatResponse>>('/chat', {
    method: 'POST',
    ...(options.lookupToken ? { headers: { 'X-Order-Lookup-Token': options.lookupToken } } : {}),
    body: JSON.stringify({
      message: message.trim(),
      history,
      ...(options.actionContext ? { action_context: options.actionContext } : {}),
    }),
  })

  return response.data
}

export const confirmChatAction = async (
  confirmationToken: string,
  clientMessageId: string,
  idempotencyKey: string,
  lookupToken?: string,
): Promise<ChatResponse> => {
  const response = await apiClient<ApiSuccess<ChatResponse>>('/chat', {
    method: 'POST',
    headers: {
      'Idempotency-Key': idempotencyKey,
      ...(lookupToken ? { 'X-Order-Lookup-Token': lookupToken } : {}),
    },
    body: JSON.stringify({
      message: 'Xác nhận thao tác',
      history: [],
      confirmation_token: confirmationToken,
      client_message_id: clientMessageId,
    }),
  })

  return response.data
}
