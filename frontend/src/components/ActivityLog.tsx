import React, { useEffect, useState } from "react"
import { api, ApiError } from "../api/client"
import type { ActivityLog } from "../api/types"
import { 
  Clock, 
  RefreshCw, 
  AlertCircle, 
  ShieldCheck, 
  CheckCircle2, 
  Copy,
  Search
} from "lucide-react"

interface ActivityLogViewProps {
  invoiceIdFilter?: string | null
  onSelectInvoice?: (invoiceId: string) => void
}

export const ActivityLogView: React.FC<ActivityLogViewProps> = ({
  invoiceIdFilter,
  onSelectInvoice,
}) => {
  const [logs, setLogs] = useState<ActivityLog[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [filterType, setFilterType] = useState<string>("ALL")
  const [searchQuery, setSearchQuery] = useState("")

  const loadLogs = async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await api.getAuditLogs(invoiceIdFilter || undefined)
      setLogs(data)
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.detail)
      } else {
        setError("Failed to load audit activity logs.")
      }
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadLogs()
  }, [invoiceIdFilter])

  const filteredLogs = logs.filter((log) => {
    if (filterType !== "ALL" && log.action_type !== filterType) return false
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase()
      const matchInv = log.invoice_id.toLowerCase().includes(q)
      const matchAction = log.action_type.toLowerCase().includes(q)
      const matchDetails = (log.details || "").toLowerCase().includes(q)
      if (!matchInv && !matchAction && !matchDetails) return false
    }
    return true
  })

  // Format distinct status labels strictly according to rule:
  // "Sent" or "Delivered" appears ONLY for verified results.
  const renderStatusBadge = (log: ActivityLog) => {
    const isVerified = log.status === "verified" || log.action_type.includes("verified")

    if (isVerified) {
      return (
        <span className="badge badge-low" style={{ display: "inline-flex", alignItems: "center", gap: "0.25rem" }}>
          <CheckCircle2 size={12} />
          <span>Verified & Sent</span>
        </span>
      )
    }

    if (log.status === "copied" || log.action_type === "copy_reminder" || log.action_type === "record_copied_reminder") {
      return (
        <span className="badge badge-demo" style={{ display: "inline-flex", alignItems: "center", gap: "0.25rem" }}>
          <Copy size={12} />
          <span>Copied / Manual Outreach</span>
        </span>
      )
    }

    if (log.status === "approved" || log.action_type === "action_approved") {
      return (
        <span className="badge badge-high" style={{ display: "inline-flex", alignItems: "center", gap: "0.25rem" }}>
          <ShieldCheck size={12} />
          <span>Approved (Pending Execution)</span>
        </span>
      )
    }

    if (log.status === "executed" || log.action_type === "action_executed") {
      return (
        <span className="badge badge-medium">
          Executed
        </span>
      )
    }

    if (log.status === "failed") {
      return (
        <span className="badge badge-critical">
          Execution Failed
        </span>
      )
    }

    return (
      <span className="badge badge-demo">
        {log.status}
      </span>
    )
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "1rem" }}>
        <div>
          <h2 style={{ fontSize: "1.25rem", fontWeight: 700, color: "var(--text-main)" }}>
            Immutable Recovery Audit Log
          </h2>
          <p style={{ fontSize: "0.8125rem", color: "var(--text-muted)" }}>
            Cryptographically tracked lifecycle events and human authorization records.
          </p>
        </div>

        <button className="btn-secondary btn-sm" onClick={loadLogs} disabled={loading}>
          <RefreshCw size={13} style={{ marginRight: "0.25rem" }} />
          Refresh Log
        </button>
      </div>

      {/* Filter and Search Bar */}
      <div className="card" style={{ padding: "0.75rem" }}>
        <div style={{ display: "flex", gap: "0.75rem", flexWrap: "wrap", alignItems: "center" }}>
          <div style={{ position: "relative", minWidth: "220px", flex: "1 1 220px" }}>
            <Search size={15} style={{ position: "absolute", left: "0.75rem", top: "50%", transform: "translateY(-50%)", color: "var(--text-muted)" }} />
            <input
              type="text"
              className="input"
              style={{ paddingLeft: "2.25rem" }}
              placeholder="Search audit trail by invoice ID or action..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: "0.375rem" }}>
            <span style={{ fontSize: "0.75rem", color: "var(--text-muted)", fontWeight: 600 }}>Action:</span>
            <select
              className="input"
              style={{ width: "auto", padding: "0.35rem 0.6rem" }}
              value={filterType}
              onChange={(e) => setFilterType(e.target.value)}
            >
              <option value="ALL">All Event Types</option>
              <option value="paypal_remind">paypal_remind</option>
              <option value="paypal_send">paypal_send</option>
              <option value="record_copied_reminder">record_copied_reminder</option>
              <option value="action_approved">action_approved</option>
              <option value="action_executed">action_executed</option>
              <option value="ai_explain">ai_explain</option>
              <option value="paypal_sync">paypal_sync</option>
            </select>
          </div>
        </div>
      </div>

      {error && (
        <div className="card" style={{ padding: "1rem", backgroundColor: "var(--priority-critical-bg)", borderColor: "var(--priority-critical-border)" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", color: "var(--priority-critical-text)" }}>
            <AlertCircle size={18} />
            <span style={{ fontWeight: 600 }}>Error loading audit logs: {error}</span>
          </div>
        </div>
      )}

      {loading ? (
        <div className="card" style={{ textAlign: "center", padding: "3rem" }}>
          <div className="spinner" style={{ width: "1.75rem", height: "1.75rem", marginBottom: "0.75rem" }} />
          <div style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>Retrieving verified audit logs...</div>
        </div>
      ) : filteredLogs.length === 0 ? (
        <div className="card" style={{ textAlign: "center", padding: "3rem" }}>
          <Clock size={36} color="var(--text-light)" style={{ marginBottom: "0.75rem" }} />
          <h3 style={{ fontSize: "1rem", color: "var(--text-main)" }}>No audit records found</h3>
          <p style={{ color: "var(--text-muted)", fontSize: "0.8125rem", marginTop: "0.25rem" }}>
            Events are recorded automatically upon proposal, approval, execution, and PayPal synchronization.
          </p>
        </div>
      ) : (
        <div className="card" style={{ padding: 0, overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", textAlign: "left", fontSize: "0.8125rem" }}>
            <thead>
              <tr style={{ backgroundColor: "var(--bg-subtle)", borderBottom: "1px solid var(--border-color)", color: "var(--text-muted)" }}>
                <th style={{ padding: "0.75rem 1rem", fontWeight: 600 }}>TIMESTAMP</th>
                <th style={{ padding: "0.75rem 1rem", fontWeight: 600 }}>INVOICE ID</th>
                <th style={{ padding: "0.75rem 1rem", fontWeight: 600 }}>ACTION TYPE</th>
                <th style={{ padding: "0.75rem 1rem", fontWeight: 600 }}>VERIFIED STATUS</th>
                <th style={{ padding: "0.75rem 1rem", fontWeight: 600 }}>DETAILS / EVIDENCE</th>
              </tr>
            </thead>
            <tbody>
              {filteredLogs.map((log) => (
                <tr
                  key={log.id}
                  style={{ borderBottom: "1px solid var(--border-color)" }}
                >
                  <td style={{ padding: "0.75rem 1rem", color: "var(--text-muted)", whiteSpace: "nowrap" }}>
                    {log.timestamp}
                  </td>
                  <td style={{ padding: "0.75rem 1rem" }}>
                    {onSelectInvoice ? (
                      <span
                        onClick={() => onSelectInvoice(log.invoice_id)}
                        style={{ fontWeight: 600, color: "var(--primary)", cursor: "pointer", textDecoration: "underline" }}
                      >
                        {log.invoice_id}
                      </span>
                    ) : (
                      <span style={{ fontWeight: 600, color: "var(--text-main)" }}>{log.invoice_id}</span>
                    )}
                  </td>
                  <td style={{ padding: "0.75rem 1rem" }}>
                    <code style={{
                      backgroundColor: "var(--bg-subtle)",
                      padding: "0.2rem 0.4rem",
                      borderRadius: "4px",
                      fontSize: "0.75rem"
                    }}>
                      {log.action_type}
                    </code>
                  </td>
                  <td style={{ padding: "0.75rem 1rem" }}>
                    {renderStatusBadge(log)}
                  </td>
                  <td style={{ padding: "0.75rem 1rem", color: "var(--text-muted)", maxWidth: "320px" }}>
                    {log.details || "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

