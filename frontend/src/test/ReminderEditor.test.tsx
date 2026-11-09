import { describe, it, expect, vi, beforeEach } from "vitest"
import { render, screen, waitFor, fireEvent } from "@testing-library/react"
import { ReminderEditor } from "../components/ReminderEditor"
import { api, ApiError } from "../api/client"
import type { InvoiceDetail, ReminderDraft, ActionProposeResponse } from "../api/types"

const mockInvoice: InvoiceDetail = {
  invoice_id: "INV2-5NY5-V2PK-CASX-WNU2",
  score: 68,
  priority: "HIGH",
  due_date: "2026-10-24",
  days_overdue: 15,
  outstanding_amount: 1200,
  total_amount: 1200,
  currency: "USD",
  status: "SENT",
  recommended_action: "firm_followup",
  action_reason: "Account 15 days overdue requires firm follow-up.",
  contributing_factors: [],
  has_assumption_flag: false,
  unavailable_data_points: [],
  customer_name: "Acme Enterprise Corp",
  customer_email: "acme@example.com",
  is_demo: false,
}

const mockDraft: ReminderDraft = {
  id: "DRAFT-TEST-001",
  invoice_id: "INV2-5NY5-V2PK-CASX-WNU2",
  tone: "firm",
  subject: "URGENT: Outstanding Balance on Invoice INV2-5NY5-V2PK-CASX-WNU2",
  body: "Your payment of USD 1,200.00 was due on 2026-10-24 and is 15 days past due. Please remit payment immediately.",
  status: "draft",
  created_at: "2026-11-09T10:00:00Z",
}

const mockProposal: ActionProposeResponse = {
  approval_id: "appr-abc-12345",
  invoice_id: "INV2-5NY5-V2PK-CASX-WNU2",
  action_type: "paypal_remind_invoice",
  status: "draft",
  hash: "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
  expires_at: "2026-11-09T10:15:00Z",
  merchant_id: "merchant_demo",
  message: "Action proposal stored with SHA-256 hash. Awaiting human merchant approval.",
}

describe("ReminderEditor & Approval Dialog", () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it("loads invoice draft, allows proposing action, and displays exact parameters & SHA-256 in approval dialog", async () => {
    vi.spyOn(api, "getInvoiceDetail").mockResolvedValue(mockInvoice)
    vi.spyOn(api, "getInvoiceReminders").mockResolvedValue([mockDraft])
    vi.spyOn(api, "proposeAction").mockResolvedValue(mockProposal)

    render(<ReminderEditor invoiceId="INV2-5NY5-V2PK-CASX-WNU2" onBack={vi.fn()} />)

    // Wait for draft content to load into form inputs
    await waitFor(() => {
      expect(screen.getByDisplayValue(/URGENT: Outstanding Balance/i)).toBeInTheDocument()
      expect(screen.getByDisplayValue(/Your payment of USD 1,200.00/i)).toBeInTheDocument()
    })

    // Click "Propose & Open Approval Dialog"
    const proposeBtn = screen.getByRole("button", { name: /Propose & Open Approval Dialog/i })
    fireEvent.click(proposeBtn)

    // Approval Modal should appear with exact parameters
    await waitFor(() => {
      expect(screen.getByText(/Human Action Approval Gate/i)).toBeInTheDocument()
      expect(screen.getByText("appr-abc-12345")).toBeInTheDocument()
      expect(screen.getByText("paypal_remind_invoice")).toBeInTheDocument()
      expect(screen.getByText(/Tamper Protection/i)).toBeInTheDocument()
      expect(screen.getByRole("button", { name: /Approve Action as Merchant/i })).toBeInTheDocument()
    })
  })

  it("renders error state when action proposal fails", async () => {
    vi.spyOn(api, "getInvoiceDetail").mockResolvedValue(mockInvoice)
    vi.spyOn(api, "getInvoiceReminders").mockResolvedValue([mockDraft])
    vi.spyOn(api, "proposeAction").mockRejectedValue(new ApiError(400, "Invalid action parameters"))

    render(<ReminderEditor invoiceId="INV2-5NY5-V2PK-CASX-WNU2" onBack={vi.fn()} />)

    await waitFor(() => {
      expect(screen.getByDisplayValue(/URGENT: Outstanding Balance/i)).toBeInTheDocument()
    })

    const proposeBtn = screen.getByRole("button", { name: /Propose & Open Approval Dialog/i })
    fireEvent.click(proposeBtn)

    await waitFor(() => {
      expect(screen.getByText(/Invalid action parameters/i)).toBeInTheDocument()
    })
  })
})
