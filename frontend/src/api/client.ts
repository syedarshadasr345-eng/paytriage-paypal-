/**
 * PayTriage API Client with in-memory auth token management
 */

import { API_BASE } from "../config"
import type {
  LoginResponse,
  QueueSummary,
  InvoiceDetail,
  StrategyComparison,
  ExplanationResponse,
  ReminderDraft,
  ActionProposeResponse,
  ActionApprovalResponse,
  ActionExecuteResponse,
  ActivityLog,
  RecoveryStats,
  AssistantResponse,
  PayPalStatus,
  ActionType,
  Tone,
} from "./types"

// IN-MEMORY TOKEN STORAGE (Strictly NOT localStorage)
let memoryToken: string | null = null

export function setAuthToken(token: string | null) {
  memoryToken = token
}

export function getAuthToken(): string | null {
  return memoryToken
}

export class ApiError extends Error {
  status: number
  detail: string

  constructor(status: number, detail: string) {
    super(detail)
    this.name = "ApiError"
    this.status = status
    this.detail = detail
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers || {})
  headers.set("Content-Type", "application/json")

  if (memoryToken) {
    headers.set("Authorization", `Bearer ${memoryToken}`)
  }

  const url = `${API_BASE}${path}`
  let res: Response
  try {
    res = await fetch(url, { ...options, headers })
  } catch (err) {
    throw new ApiError(0, `Network failure connecting to backend: ${err instanceof Error ? err.message : String(err)}`)
  }

  if (!res.ok) {
    let detail = `Server returned HTTP ${res.status}`
    try {
      const errJson = await res.json()
      if (errJson && errJson.detail) {
        detail = typeof errJson.detail === "string" ? errJson.detail : JSON.stringify(errJson.detail)
      }
    } catch {
      // Non-JSON error body
    }
    throw new ApiError(res.status, detail)
  }

  // Handle 204 or empty response
  if (res.status === 204) {
    return {} as T
  }

  return res.json()
}

export const api = {
  // Auth
  login: (username: string, password: string): Promise<LoginResponse> =>
    request<LoginResponse>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    }),

  getMe: () => request<{ username: string; role: string; merchant_id: string }>("/api/auth/me"),

  // Recovery Queue & Stats
  getStats: (): Promise<RecoveryStats> =>
    request<RecoveryStats>("/api/recovery/stats"),

  getQueue: (includeNotDue = true): Promise<QueueSummary> =>
    request<QueueSummary>(`/api/recovery/queue?include_not_due=${includeNotDue}`),

  getInvoiceDetail: (invoiceId: string): Promise<InvoiceDetail> =>
    request<InvoiceDetail>(`/api/recovery/invoices/${encodeURIComponent(invoiceId)}`),

  getInvoiceStrategies: (invoiceId: string): Promise<StrategyComparison> =>
    request<StrategyComparison>(`/api/recovery/invoices/${encodeURIComponent(invoiceId)}/strategies`),

  // AI Explain
  explainInvoice: (invoiceId: string, question?: string, today?: string): Promise<ExplanationResponse> => {
    const qParam = today ? `?today=${encodeURIComponent(today)}` : ""
    return request<ExplanationResponse>(`/api/ai/invoices/${encodeURIComponent(invoiceId)}/explain${qParam}`, {
      method: "POST",
      body: JSON.stringify(question ? { question } : {}),
    })
  },

  // Reminders
  generateReminder: (invoiceId: string, tone?: Tone): Promise<ReminderDraft> =>
    request<ReminderDraft>(`/api/ai/invoices/${encodeURIComponent(invoiceId)}/reminder`, {
      method: "POST",
      body: JSON.stringify(tone ? { tone } : {}),
    }),

  getInvoiceReminders: (invoiceId: string): Promise<ReminderDraft[]> =>
    request<ReminderDraft[]>(`/api/ai/invoices/${encodeURIComponent(invoiceId)}/reminders`),

  editReminder: (reminderId: string, subject: string, body: string): Promise<ReminderDraft> =>
    request<ReminderDraft>(`/api/ai/reminders/${encodeURIComponent(reminderId)}`, {
      method: "PUT",
      body: JSON.stringify({ subject, body }),
    }),

  copyReminder: (reminderId: string): Promise<{ status: string; message: string }> =>
    request<{ status: string; message: string }>(`/api/ai/reminders/${encodeURIComponent(reminderId)}/copy`, {
      method: "POST",
    }),

  // Approval Gate & Action Execution
  proposeAction: (invoiceId: string, actionType: ActionType, parameters: Record<string, any>): Promise<ActionProposeResponse> =>
    request<ActionProposeResponse>("/api/actions/propose", {
      method: "POST",
      body: JSON.stringify({ invoice_id: invoiceId, action_type: actionType, parameters }),
    }),

  approveAction: (approvalId: string): Promise<ActionApprovalResponse> =>
    request<ActionApprovalResponse>(`/api/actions/${encodeURIComponent(approvalId)}/approve`, {
      method: "POST",
    }),

  executeAction: (approvalId: string, actionType: ActionType, parameters: Record<string, any>): Promise<ActionExecuteResponse> =>
    request<ActionExecuteResponse>(`/api/actions/${encodeURIComponent(approvalId)}/execute`, {
      method: "POST",
      body: JSON.stringify({ action_type: actionType, parameters }),
    }),

  listApprovals: (invoiceId?: string): Promise<any[]> => {
    const qParam = invoiceId ? `?invoice_id=${encodeURIComponent(invoiceId)}` : ""
    return request<any[]>(`/api/actions${qParam}`)
  },

  // Audit Logs
  getAuditLogs: (invoiceId?: string): Promise<ActivityLog[]> => {
    const qParam = invoiceId ? `?invoice_id=${encodeURIComponent(invoiceId)}` : ""
    return request<ActivityLog[]>(`/api/recovery/audit-logs${qParam}`)
  },

  // Interactive Assistant
  askAssistant: (query: string): Promise<AssistantResponse> =>
    request<AssistantResponse>("/api/ai/assistant/query", {
      method: "POST",
      body: JSON.stringify({ query }),
    }),

  // PayPal Status
  getPayPalStatus: (): Promise<PayPalStatus> =>
    request<PayPalStatus>("/api/paypal/status"),
}

