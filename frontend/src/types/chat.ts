export type ChatRole = 'user' | 'assistant'
export type ChatStatus = 'ok' | 'insufficient_data' | 'out_of_scope' | 'provider_unavailable'

export interface ChatHistoryItem {
  role: ChatRole
  content: string
}

export interface ChatProduct {
  id: string
  slug: string
  name: string
  image_url: string | null
  effective_price: number
  available_colors: string[]
  available_sizes: string[]
  in_stock: boolean
  url: string
}

export interface ChatSource {
  source_type: 'product' | 'knowledge'
  source_id: string
  rag_document_id: string
  chunk_ids: string[]
  product_id: string | null
  knowledge_type: 'return_policy' | null
  title: string
}

export type ChatMutationAction = 'cart_add' | 'cart_update' | 'cart_remove' | 'order_create' | 'order_cancel' | 'refund_request'

export interface ChatProposedAction {
  action: ChatMutationAction
  resource_code: string
  summary: string
  requires_confirmation: true
  confirmation_token: string
  expires_at: string
}

export interface ChatResponse {
  answer: string
  products: ChatProduct[]
  sources: ChatSource[]
  status: ChatStatus
  proposed_action: ChatProposedAction | null
}
