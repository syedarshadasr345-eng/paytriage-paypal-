import React, { useEffect, useState, useMemo } from "react"
import { api, ApiError } from "../api/client"
import type { QueueItem, Priority } from "../api/types"
import { 
  ArrowUpDown, 
  Search, 
  RefreshCw, 
  AlertCircle,
  ChevronRight,
  ShieldAlert
} from "lucide-react"

interface RecoveryCenterProps {
  onSelectInvoice: (invoiceId: string) => void
  selectedInvoiceId?: string | null
}

export const RecoveryCenter: React.FC<RecoveryCenterProps> = ({
  onSelectInvoice,
  selectedInvoiceId,
}) => {
  const [items, setItems] = useState<QueueItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Filters & Sorting state
  const [searchQuery, setSearchQuery] = useState("")
  const [priorityFilter, setPriorityFilter] = useState<string>("ALL")
  const [statusFilter, setStatusFilter] = useState<string>("ALL")
  const [actionFilter, setActionFilter] = useState<string>("ALL")
  const [dataSourceFilter, setDataSourceFilter] = useState<string>("ALL")
  const [sortBy, setSortBy] = useState<"score" | "amount" | "overdue">("score")
  const [sortDirection, setSortDirection] = useState<"desc" | "asc">("desc")

  const loadQueue = async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await api.getQueue(true)
      setItems(data.items)
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.detail)
      } else {
        setError("Unable to load recovery queue from server.")
      }
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadQueue()
  }, [])

  // Filtered and sorted items
  const filteredItems = useMemo(() => {
    return items
      .filter((item) => {
        // Search
        if (searchQuery.trim()) {
          const q = searchQuery.toLowerCase()
          const invId = (item.id || item.invoice_id || "").toLowerCase()
          const matchId = invId.includes(q)
          const matchNum = item.invoice_number.toLowerCase().includes(q)
          const matchCust = item.customer_name.toLowerCase().includes(q)
          if (!matchId && !matchNum && !matchCust) return false
        }
        // Priority
        if (priorityFilter !== "ALL" && item.priority !== priorityFilter) return false
        // Status
        if (statusFilter !== "ALL") {
          if (statusFilter === "OVERDUE" && item.days_overdue <= 0) return false
          if (statusFilter === "NOT_OVERDUE" && item.days_overdue > 0) return false
          if (statusFilter === "PAID" && item.status !== "PAID") return false
        }
        // Action
        if (actionFilter !== "ALL" && item.recommended_action !== actionFilter) return false
        // Data source (Live Sandbox vs Demo)
        if (dataSourceFilter === "LIVE" && item.is_demo) return false
        if (dataSourceFilter === "DEMO" && !item.is_demo) return false

        return true
      })
      .sort((a, b) => {
        let cmp = 0
        if (sortBy === "score") {
          cmp = (b.score || 0) - (a.score || 0)
        } else if (sortBy === "amount") {
          cmp = (b.outstanding_amount || 0) - (a.outstanding_amount || 0)
        } else if (sortBy === "overdue") {
          cmp = (b.days_overdue || 0) - (a.days_overdue || 0)
        }
        return sortDirection === "desc" ? cmp : -cmp
      })
  }, [items, searchQuery, priorityFilter, statusFilter, actionFilter, dataSourceFilter, sortBy, sortDirection])

  const formatCurrency = (val: number, cur = "USD") => {
    return new Intl.NumberFormat("en-US", { style: "currency", currency: cur }).format(val)
  }

  const getPriorityBadgeClass = (priority: Priority) => {
    switch (priority) {
      case "CRITICAL": return "badge-critical"
      case "HIGH": return "badge-high"
      case "MEDIUM": return "badge-medium"
      case "LOW": return "badge-low"
      default: return "badge-demo"
    }
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
      {/* Header & Controls */}
      <div style={{
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
        flexWrap: "wrap",
        gap: "1rem"
      }}>
        <div>
          <h2 style={{ fontSize: "1.25rem", fontWeight: 700, color: "var(--text-main)" }}>
            Recovery Center & Prioritized Queue
          </h2>
          <p style={{ fontSize: "0.8125rem", color: "var(--text-muted)" }}>
            Deterministically ranked by recovery score (0–100) combining aging, balance, reminders, and history.
          </p>
        </div>
        <button className="btn-secondary btn-sm" onClick={loadQueue} disabled={loading}>
          <RefreshCw size={13} style={{ marginRight: "0.25rem" }} />
          Reload Queue
        </button>
      </div>

      {/* Filter and Search Bar */}
      <div className="card" style={{ padding: "0.875rem" }}>
        <div style={{
          display: "flex",
          gap: "0.75rem",
          flexWrap: "wrap",
          alignItems: "center"
        }}>
          {/* Search */}
          <div style={{ position: "relative", minWidth: "220px", flex: "1 1 220px" }}>
            <Search size={15} style={{ position: "absolute", left: "0.75rem", top: "50%", transform: "translateY(-50%)", color: "var(--text-muted)" }} />
            <input
              type="text"
              className="input"
              style={{ paddingLeft: "2.25rem" }}
              placeholder="Search by ID, number, or customer..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
          </div>

          {/* Priority filter */}
          <div style={{ display: "flex", alignItems: "center", gap: "0.375rem" }}>
            <span style={{ fontSize: "0.75rem", color: "var(--text-muted)", fontWeight: 600 }}>Priority:</span>
            <select
              className="input"
              style={{ width: "auto", padding: "0.35rem 0.6rem" }}
              value={priorityFilter}
              onChange={(e) => setPriorityFilter(e.target.value)}
            >
              <option value="ALL">All Priorities</option>
              <option value="CRITICAL">Critical</option>
              <option value="HIGH">High</option>
              <option value="MEDIUM">Medium</option>
              <option value="LOW">Low</option>
            </select>
          </div>

          {/* Status filter */}
          <div style={{ display: "flex", alignItems: "center", gap: "0.375rem" }}>
            <span style={{ fontSize: "0.75rem", color: "var(--text-muted)", fontWeight: 600 }}>Status:</span>
            <select
              className="input"
              style={{ width: "auto", padding: "0.35rem 0.6rem" }}
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
            >
              <option value="ALL">All Statuses</option>
              <option value="OVERDUE">Overdue Only</option>
              <option value="NOT_OVERDUE">Not Overdue</option>
              <option value="PAID">Paid / Settled</option>
            </select>
          </div>

          {/* Action filter */}
          <div style={{ display: "flex", alignItems: "center", gap: "0.375rem" }}>
            <span style={{ fontSize: "0.75rem", color: "var(--text-muted)", fontWeight: 600 }}>Action:</span>
            <select
              className="input"
              style={{ width: "auto", padding: "0.35rem 0.6rem" }}
              value={actionFilter}
              onChange={(e) => setActionFilter(e.target.value)}
            >
              <option value="ALL">All Actions</option>
              <option value="polite_reminder">Polite Reminder</option>
              <option value="firm_followup">Firm Follow-up</option>
              <option value="manual_review">Manual Review</option>
              <option value="schedule_later_followup">Scheduled Follow-up</option>
              <option value="wait_for_response">Wait for Response</option>
              <option value="no_action">No Action</option>
            </select>
          </div>

          {/* Source filter */}
          <div style={{ display: "flex", alignItems: "center", gap: "0.375rem" }}>
            <span style={{ fontSize: "0.75rem", color: "var(--text-muted)", fontWeight: 600 }}>Source:</span>
            <select
              className="input"
              style={{ width: "auto", padding: "0.35rem 0.6rem" }}
              value={dataSourceFilter}
              onChange={(e) => setDataSourceFilter(e.target.value)}
            >
              <option value="ALL">All Invoices</option>
              <option value="LIVE">Live Sandbox Only</option>
              <option value="DEMO">Demo Data Only</option>
            </select>
          </div>

          {/* Sorting */}
          <div style={{ display: "flex", alignItems: "center", gap: "0.375rem", marginLeft: "auto" }}>
            <span style={{ fontSize: "0.75rem", color: "var(--text-muted)", fontWeight: 600 }}>Sort:</span>
            <select
              className="input"
              style={{ width: "auto", padding: "0.35rem 0.6rem" }}
              value={sortBy}
              onChange={(e) => setSortBy(e.target.value as any)}
            >
              <option value="score">Recovery Score</option>
              <option value="amount">Outstanding Amount</option>
              <option value="overdue">Days Overdue</option>
            </select>
            <button
              className="btn-secondary btn-sm"
              style={{ padding: "0.35rem 0.5rem" }}
              onClick={() => setSortDirection(sortDirection === "desc" ? "asc" : "desc")}
              title={`Sorting ${sortDirection === "desc" ? "Descending" : "Ascending"}`}
            >
              <ArrowUpDown size={13} />
            </button>
          </div>
        </div>
      </div>

      {/* Queue Table */}
      {error && (
        <div className="card" style={{ padding: "1rem", backgroundColor: "var(--priority-critical-bg)", borderColor: "var(--priority-critical-border)" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", color: "var(--priority-critical-text)" }}>
            <AlertCircle size={18} />
            <span style={{ fontWeight: 600 }}>Failed to load queue: {error}</span>
          </div>
        </div>
      )}

      {loading ? (
        <div className="card" style={{ textAlign: "center", padding: "3rem" }}>
          <div className="spinner" style={{ width: "1.75rem", height: "1.75rem", marginBottom: "0.75rem" }} />
          <div style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>Computing recovery priority queue...</div>
        </div>
      ) : filteredItems.length === 0 ? (
        <div className="card" style={{ textAlign: "center", padding: "3rem" }}>
          <ShieldAlert size={36} color="var(--text-light)" style={{ marginBottom: "0.75rem" }} />
          <h3 style={{ fontSize: "1rem", color: "var(--text-main)" }}>No matching invoices found</h3>
          <p style={{ color: "var(--text-muted)", fontSize: "0.8125rem", marginTop: "0.25rem" }}>
            Adjust your search or active filter settings.
          </p>
        </div>
      ) : (
        <div className="card" style={{ padding: 0, overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", textAlign: "left", fontSize: "0.8125rem" }}>
            <thead>
              <tr style={{ backgroundColor: "var(--bg-subtle)", borderBottom: "1px solid var(--border-color)", color: "var(--text-muted)" }}>
                <th style={{ padding: "0.75rem 1rem", fontWeight: 600 }}>SCORE / PRIORITY</th>
                <th style={{ padding: "0.75rem 1rem", fontWeight: 600 }}>INVOICE</th>
                <th style={{ padding: "0.75rem 1rem", fontWeight: 600 }}>CUSTOMER</th>
                <th style={{ padding: "0.75rem 1rem", fontWeight: 600 }}>OUTSTANDING</th>
                <th style={{ padding: "0.75rem 1rem", fontWeight: 600 }}>DUE / AGING</th>
                <th style={{ padding: "0.75rem 1rem", fontWeight: 600 }}>RECOMMENDED ACTION</th>
                <th style={{ padding: "0.75rem 1rem", fontWeight: 600 }}>SOURCE</th>
                <th style={{ padding: "0.75rem 1rem", fontWeight: 600, textAlign: "right" }}>TRIAGE</th>
              </tr>
            </thead>
            <tbody>
              {filteredItems.map((item) => {
                const invId = item.id || item.invoice_id || ""
                const isSelected = selectedInvoiceId === invId
                return (
                  <tr
                    key={invId}
                    onClick={() => onSelectInvoice(invId)}
                    style={{
                      borderBottom: "1px solid var(--border-color)",
                      backgroundColor: isSelected ? "var(--primary-light)" : "transparent",
                      cursor: "pointer",
                      transition: "background-color 0.1s"
                    }}
                    onMouseEnter={(e) => {
                      if (!isSelected) e.currentTarget.style.backgroundColor = "var(--bg-subtle)"
                    }}
                    onMouseLeave={(e) => {
                      if (!isSelected) e.currentTarget.style.backgroundColor = "transparent"
                    }}
                  >
                    {/* Score & Priority */}
                    <td style={{ padding: "0.875rem 1rem" }}>
                      <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                        <span style={{
                          display: "inline-block",
                          width: "32px",
                          textAlign: "center",
                          fontWeight: 700,
                          fontSize: "0.9375rem",
                          color: "var(--text-main)"
                        }}>
                          {item.score ?? "—"}
                        </span>
                        <span className={`badge ${getPriorityBadgeClass(item.priority)}`}>
                          {item.priority}
                        </span>
                      </div>
                    </td>

                    {/* Invoice ID / Number */}
                    <td style={{ padding: "0.875rem 1rem" }}>
                      <div style={{ fontWeight: 600, color: "var(--text-main)" }}>
                        {invId}
                      </div>
                      <div style={{ color: "var(--text-muted)", fontSize: "0.75rem" }}>
                        {item.invoice_number}
                      </div>
                    </td>

                    {/* Customer */}
                    <td style={{ padding: "0.875rem 1rem" }}>
                      <div style={{ fontWeight: 500, color: "var(--text-main)" }}>
                        {item.customer_name}
                      </div>
                      {item.customer_email && (
                        <div style={{ color: "var(--text-muted)", fontSize: "0.75rem" }}>
                          {item.customer_email}
                        </div>
                      )}
                    </td>

                    {/* Outstanding Amount */}
                    <td style={{ padding: "0.875rem 1rem" }}>
                      <div style={{ fontWeight: 700, color: "var(--text-main)" }}>
                        {formatCurrency(item.outstanding_amount, item.currency)}
                      </div>
                      <div style={{ color: "var(--text-muted)", fontSize: "0.75rem" }}>
                        Total: {formatCurrency(item.total_amount, item.currency)}
                      </div>
                    </td>

                    {/* Due Date & Aging */}
                    <td style={{ padding: "0.875rem 1rem" }}>
                      <div style={{
                        fontWeight: 600,
                        color: item.days_overdue > 0 ? "var(--priority-critical-text)" : "var(--text-main)"
                      }}>
                        {item.days_overdue > 0
                          ? `${item.days_overdue}d overdue`
                          : item.days_overdue === 0
                          ? "Due today"
                          : `Due in ${Math.abs(item.days_overdue)}d`}
                      </div>
                      <div style={{ color: "var(--text-muted)", fontSize: "0.75rem" }}>
                        {item.due_date}
                      </div>
                    </td>

                    {/* Recommended Action */}
                    <td style={{ padding: "0.875rem 1rem", maxWidth: "260px" }}>
                      <div style={{ fontWeight: 600, color: "var(--text-main)" }}>
                        {item.recommended_action.replace(/_/g, " ")}
                      </div>
                      <div style={{
                        color: "var(--text-muted)",
                        fontSize: "0.75rem",
                        whiteSpace: "nowrap",
                        overflow: "hidden",
                        textOverflow: "ellipsis"
                      }} title={item.action_reason}>
                        {item.action_reason}
                      </div>
                    </td>

                    {/* Source: Live Sandbox vs Demo */}
                    <td style={{ padding: "0.875rem 1rem" }}>
                      {item.is_demo ? (
                        <span className="badge badge-demo">DEMO DATA</span>
                      ) : (
                        <span className="badge badge-sandbox">LIVE SANDBOX</span>
                      )}
                    </td>

                    {/* Action Arrow */}
                    <td style={{ padding: "0.875rem 1rem", textAlign: "right" }}>
                      <button
                        className="btn-secondary btn-sm"
                        style={{ display: "inline-flex", alignItems: "center", gap: "0.25rem" }}
                        onClick={(e) => {
                          e.stopPropagation()
                          onSelectInvoice(invId)
                        }}
                      >
                        <span>Examine</span>
                        <ChevronRight size={13} />
                      </button>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

