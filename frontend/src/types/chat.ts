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
  product_id: string
  rag_document_id: string
  chunk_ids: string[]
}

export interface ChatResponse {
  answer: string
  products: ChatProduct[]
  sources: ChatSource[]
  status: ChatStatus
}
