import { describe, it, expect, vi, beforeEach } from "vitest"
import { render, screen, waitFor, fireEvent } from "@testing-library/react"
import { RecoveryCenter } from "../components/RecoveryCenter"
import { api, ApiError } from "../api/client"
import type { QueueSummary } from "../api/types"

const mockQueue: QueueSummary = {
  total_evaluated: 2,
  total_outstanding_usd: 8700,
  items: [
    {
      id: "INV2-5NY5-V2PK-CASX-WNU2",
      invoice_id: "INV2-5NY5-V2PK-CASX-WNU2",
      invoice_number: "INV-SANDBOX-001",
      customer_name: "Acme Enterprise Corp",
      customer_email: "acme@example.com",
      currency: "USD",
      total_amount: 1200,
      outstanding_amount: 1200,
      due_date: "2026-10-24",
      days_overdue: 15,
      status: "OVERDUE",
      score: 68,
      priority: "HIGH",
      recommended_action: "firm_followup",
      action_reason: "Account 15 days overdue requires firm follow-up.",
      action_status: "ready",
      is_demo: false,
    },
    {
      id: "INV-NEW-006",
      invoice_id: "INV-NEW-006",
      invoice_number: "INV-2026-006",
      customer_name: "Starlight Digital Ltd",
      customer_email: "billing@starlight.example.com",
      currency: "USD",
      total_amount: 350,
      outstanding_amount: 350,
      due_date: "2026-10-29",
      days_overdue: 3,
      status: "OVERDUE",
      score: 15,
      priority: "LOW",
      recommended_action: "polite_reminder",
      action_reason: "Newly overdue (1-7 days) with no prior reminders.",
      action_status: "ready",
      is_demo: true,
    },
  ],
}

describe("RecoveryCenter Component", () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it("loads and displays the recovery queue with scores and priority badges", async () => {
    vi.spyOn(api, "getQueue").mockResolvedValue(mockQueue)
    const onSelect = vi.fn()

    render(<RecoveryCenter onSelectInvoice={onSelect} />)

    // Verify loading indicator appears
    expect(screen.getByText(/computing recovery priority queue/i)).toBeInTheDocument()

    // Wait for queue items to render
    await waitFor(() => {
      expect(screen.getByText("INV2-5NY5-V2PK-CASX-WNU2")).toBeInTheDocument()
      expect(screen.getByText("INV-NEW-006")).toBeInTheDocument()
    })

    // Check Live Sandbox badge vs Demo Data badge
    expect(screen.getByText("LIVE SANDBOX")).toBeInTheDocument()
    expect(screen.getByText("DEMO DATA")).toBeInTheDocument()

    // Check priority tags
    expect(screen.getByText("HIGH")).toBeInTheDocument()
    expect(screen.getByText("LOW")).toBeInTheDocument()

    // Click on invoice row triggers selection
    fireEvent.click(screen.getByText("INV2-5NY5-V2PK-CASX-WNU2"))
    expect(onSelect).toHaveBeenCalledWith("INV2-5NY5-V2PK-CASX-WNU2")
  })

  it("renders error state when queue API fails", async () => {
    vi.spyOn(api, "getQueue").mockRejectedValue(new ApiError(500, "Backend database unreachable"))

    render(<RecoveryCenter onSelectInvoice={vi.fn()} />)

    await waitFor(() => {
      expect(screen.getByText(/Backend database unreachable/i)).toBeInTheDocument()
    })
  })
})

