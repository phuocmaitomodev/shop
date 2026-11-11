import type { OrderSummary, RefundRequest } from './commerce'

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

export type ChatActionContext =
  | { action: 'cart_add'; cart_id: string; variant_id: string; quantity: number }
  | { action: 'cart_update'; cart_id: string; cart_item_id: string; cart_version: number; quantity: number }
  | { action: 'cart_remove'; cart_id: string; cart_item_id: string; cart_version: number }
  | {
      action: 'order_create'
      cart_id: string
      cart_version: number
      recipient: { name: string; phone: string }
      address: { address_line: string; ward: string | null; district: string | null; province: string; note: string | null }
      payment_method: 'cod' | 'online_demo'
      coupon_code: string | null
    }
  | { action: 'order_cancel'; order_id: string; order_code: string | null; reason: string | null }
  | {
      action: 'refund_request'
      order_id: string
      order_code: string | null
      reason_code: 'manufacturer_fault' | 'transit_damage' | 'wrong_item' | 'other'
      reason_detail: string | null
    }

export interface ChatProposedAction {
  action: ChatMutationAction
  resource_code: string
  summary: string
  requires_confirmation: true
  confirmation_token: string
  expires_at: string
}

export type ChatActionResult =
  | { action: 'order_create'; order: OrderSummary }
  | { action: 'order_cancel'; order: OrderSummary }
  | { action: 'refund_request'; refund: RefundRequest }

export interface ChatResponse {
  answer: string
  products: ChatProduct[]
  sources: ChatSource[]
  status: ChatStatus
  proposed_action: ChatProposedAction | null
  action_result: ChatActionResult | null
}
