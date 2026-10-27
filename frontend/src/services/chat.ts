import type { ApiSuccess } from '../types/api'
import type { ChatHistoryItem, ChatResponse } from '../types/chat'
import { apiClient } from './api-client'

export const sendChatMessage = async (
  message: string,
  history: ChatHistoryItem[] = [],
): Promise<ChatResponse> => {
  const response = await apiClient<ApiSuccess<ChatResponse>>('/chat', {
    method: 'POST',
    body: JSON.stringify({ message: message.trim(), history }),
  })

  return response.data
}
