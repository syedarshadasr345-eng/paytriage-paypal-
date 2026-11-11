/**
 * PayTriage Frontend API Type Definitions
 */

export type Priority = "CRITICAL" | "HIGH" | "MEDIUM" | "LOW"
export type ActionType = "record_copied_reminder" | "paypal_send_invoice" | "paypal_remind_invoice"
export type ApprovalStatus = "draft" | "copied" | "approved" | "executed" | "verified" | "failed" | "expired" | "rejected"
export type Tone = "professional" | "friendly" | "polite" | "firm"

export interface User {
  username: string
  role: "merchant" | "ai_agent"
  merchant_id: string
}

export interface LoginResponse {
  access_token: string
  token_type: string
  user: User
}

export interface ScoreFactor {
  factor_name: string
  points: number
  description: string
}

export interface QueueItem {
  id: string
  invoice_id?: string
  invoice_number: string
  customer_name: string
  customer_email?: string
  currency: string
  total_amount: number
  outstanding_amount: number
  due_date: string
  days_overdue: number
  status: string
  score: number
  priority: Priority
  recommended_action: string
  action_reason: string
  action_status: string
  is_demo: boolean
  has_active_approval?: boolean
}

export interface QueueSummary {
  total_evaluated: number
  total_outstanding_usd: number
  items: QueueItem[]
}

export interface InvoiceDetail {
  id?: string
  invoice_id?: string
  score: number
  priority: Priority
  due_date: string
  days_overdue: number
  outstanding_amount: number
  total_amount: number
  currency: string
  status: string
  recommended_action: string
  action_reason: string
  contributing_factors?: ScoreFactor[]
  has_assumption_flag?: boolean
  assumption_reason?: string
  unavailable_information?: string[]
  unavailable_data_points?: string[]
  customer_name?: string
  customer_email?: string
  is_demo?: boolean
}

export interface StrategyItem {
  strategy_id: string
  name: string
  classification: "recommended" | "alternative" | "discouraged"
  recommended_timing: string
  tone: string
  advantages: string
  limitations: string
  action_payload_type: string
}

export interface StrategyComparison {
  invoice_id: string
  recommended_strategy: string
  reason: string
  strategies: StrategyItem[]
}

export interface ExplanationResponse {
  invoice_id: string
  summary: string
  key_factors: string[]
  recommended_action: string
  unavailable_information: string[]
  caveats: string[]
  source: "ai" | "template_fallback"
  fallback_reason?: string
  confidence_note: string
  generated_at: string
}

export interface ReminderDraft {
  id: string
  invoice_id: string
  tone: Tone
  subject: string
  body: string
  status: string
  created_at: string
}

export interface ActionProposeResponse {
  approval_id: string
  invoice_id: string
  action_type: ActionType
  status: ApprovalStatus
  hash: string
  expires_at: string
  merchant_id: string
  message: string
}

export interface ActionApprovalResponse {
  approval_id: string
  status: ApprovalStatus
  hash: string
  approved_by: string
  approved_at: string
  message: string
}

export interface ActionExecuteResponse {
  approval_id: string
  status: ApprovalStatus
  verified: boolean
  hash: string
  used_at: string
  execution_result: Record<string, any>
  message: string
}

export interface ActivityLog {
  id: number
  invoice_id: string
  action_type: string
  status: string
  details?: string
  timestamp: string
}

export interface RecoveryStats {
  total_invoices: number
  paid_invoices: number
  unpaid_invoices: number
  overdue_invoices: number
  total_outstanding_usd: number
  high_priority_count: number
  live_sandbox_count: number
  demo_count: number
  recent_activity: ActivityLog[]
}

export interface AssistantResponse {
  answer: string
  intent: string
  referenced_invoice_ids: string[]
  actionable_suggestions: string[]
}

export interface PayPalStatus {
  configured: boolean
  mode: string
  api_base: string
  status_label: "ready" | "not_configured"
  client_id_preview: string
  message: string
}

