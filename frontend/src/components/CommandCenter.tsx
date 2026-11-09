import React, { useEffect, useState } from "react"
import { api, ApiError } from "../api/client"
import type { RecoveryStats } from "../api/types"
import { 
  DollarSign, 
  AlertCircle, 
  TrendingUp, 
  CheckCircle, 
  ArrowRight,
  RefreshCw,
  Clock
} from "lucide-react"

interface CommandCenterProps {
  onNavigateToQueue: () => void
  onSelectInvoice: (invoiceId: string) => void
}

export const CommandCenter: React.FC<CommandCenterProps> = ({
  onNavigateToQueue,
  onSelectInvoice,
}) => {
  const [stats, setStats] = useState<RecoveryStats | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const loadStats = async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await api.getStats()
      setStats(data)
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.detail)
      } else {
        setError("Unable to load recovery command metrics from backend.")
      }
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadStats()
  }, [])

  if (loading) {
    return (
      <div style={{ display: "flex", justifyContent: "center", alignItems: "center", minHeight: "300px" }}>
        <div style={{ textAlign: "center" }}>
          <div className="spinner" style={{ width: "2rem", height: "2rem", marginBottom: "0.75rem" }} />
          <div style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>Aggregating live recovery metrics...</div>
        </div>
      </div>
    )
  }

  if (error || !stats) {
    return (
      <div className="card" style={{ textAlign: "center", padding: "2rem" }}>
        <AlertCircle size={32} color="var(--priority-critical-text)" style={{ marginBottom: "0.5rem" }} />
        <h3 style={{ fontSize: "1.125rem", color: "var(--text-main)" }}>Command Center Unavailable</h3>
        <p style={{ color: "var(--text-muted)", fontSize: "0.875rem", margin: "0.5rem 0 1rem" }}>
          {error || "No stats returned by server."}
        </p>
        <button className="btn-primary" onClick={loadStats}>
          <RefreshCw size={14} style={{ marginRight: "0.375rem" }} />
          Retry
        </button>
      </div>
    )
  }

  const formatCurrency = (amount: number) => {
    return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(amount)
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
      {/* Top Banner */}
      <div style={{
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
        flexWrap: "wrap",
        gap: "1rem"
      }}>
        <div>
          <h2 style={{ fontSize: "1.25rem", fontWeight: 700, color: "var(--text-main)" }}>
            Recovery Command Overview
          </h2>
          <p style={{ fontSize: "0.8125rem", color: "var(--text-muted)" }}>
            Real-time portfolio intelligence computed from verified backend and PayPal Sandbox records.
          </p>
        </div>
        <div style={{ display: "flex", gap: "0.75rem" }}>
          <button className="btn-secondary" onClick={loadStats}>
            <RefreshCw size={14} style={{ marginRight: "0.375rem" }} />
            Refresh
          </button>
          <button className="btn-primary" onClick={onNavigateToQueue}>
            <span>Open Triage Queue</span>
            <ArrowRight size={14} style={{ marginLeft: "0.375rem" }} />
          </button>
        </div>
      </div>

      {/* KPI Cards Grid */}
      <div style={{
        display: "grid",
        gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
        gap: "1rem"
      }}>
        {/* Outstanding Balance */}
        <div className="card" style={{ borderLeft: "4px solid var(--primary)" }}>
          <div style={{ display: "flex", justifyContent: "space-between", color: "var(--text-muted)", fontSize: "0.75rem", fontWeight: 600 }}>
            <span>TOTAL OUTSTANDING</span>
            <DollarSign size={16} color="var(--primary)" />
          </div>
          <div style={{ fontSize: "1.625rem", fontWeight: 700, color: "var(--text-main)", marginTop: "0.5rem" }}>
            {formatCurrency(stats.total_outstanding_usd)}
          </div>
          <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginTop: "0.25rem" }}>
            Across {stats.unpaid_invoices} unpaid invoice{stats.unpaid_invoices === 1 ? "" : "s"}
          </div>
        </div>

        {/* Overdue Count */}
        <div className="card" style={{ borderLeft: "4px solid var(--priority-high-text)" }}>
          <div style={{ display: "flex", justifyContent: "space-between", color: "var(--text-muted)", fontSize: "0.75rem", fontWeight: 600 }}>
            <span>OVERDUE INVOICES</span>
            <AlertCircle size={16} color="var(--priority-high-text)" />
          </div>
          <div style={{ fontSize: "1.625rem", fontWeight: 700, color: "var(--text-main)", marginTop: "0.5rem" }}>
            {stats.overdue_invoices}
          </div>
          <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginTop: "0.25rem" }}>
            Past contractual due date
          </div>
        </div>

        {/* High & Critical Priority */}
        <div className="card" style={{ borderLeft: "4px solid var(--priority-critical-text)" }}>
          <div style={{ display: "flex", justifyContent: "space-between", color: "var(--text-muted)", fontSize: "0.75rem", fontWeight: 600 }}>
            <span>HIGH / CRITICAL PRIORITY</span>
            <TrendingUp size={16} color="var(--priority-critical-text)" />
          </div>
          <div style={{ fontSize: "1.625rem", fontWeight: 700, color: "var(--text-main)", marginTop: "0.5rem" }}>
            {stats.high_priority_count}
          </div>
          <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginTop: "0.25rem" }}>
            Score ≥ 50 requiring immediate focus
          </div>
        </div>

        {/* Live PayPal vs Demo */}
        <div className="card" style={{ borderLeft: "4px solid #059669" }}>
          <div style={{ display: "flex", justifyContent: "space-between", color: "var(--text-muted)", fontSize: "0.75rem", fontWeight: 600 }}>
            <span>PAYPAL SANDBOX LIVE</span>
            <CheckCircle size={16} color="#059669" />
          </div>
          <div style={{ fontSize: "1.625rem", fontWeight: 700, color: "var(--text-main)", marginTop: "0.5rem" }}>
            {stats.live_sandbox_count}
          </div>
          <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginTop: "0.25rem" }}>
            Plus {stats.demo_count} seeded benchmark invoices
          </div>
        </div>
      </div>

      {/* Portfolio Status Summary */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))", gap: "1rem" }}>
        <div className="card">
          <h3 style={{ fontSize: "0.9375rem", fontWeight: 600, color: "var(--text-main)", marginBottom: "1rem" }}>
            Portfolio Status Distribution
          </h3>
          <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <span style={{ fontSize: "0.8125rem", color: "var(--text-muted)" }}>Total Tracked Invoices</span>
              <span style={{ fontWeight: 600, fontSize: "0.875rem" }}>{stats.total_invoices}</span>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <span style={{ fontSize: "0.8125rem", color: "var(--text-muted)" }}>Fully Paid / Settled</span>
              <span style={{ fontWeight: 600, fontSize: "0.875rem", color: "#16a34a" }}>{stats.paid_invoices}</span>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <span style={{ fontSize: "0.8125rem", color: "var(--text-muted)" }}>Unpaid & In Recovery</span>
              <span style={{ fontWeight: 600, fontSize: "0.875rem", color: "var(--primary)" }}>{stats.unpaid_invoices}</span>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <span style={{ fontSize: "0.8125rem", color: "var(--text-muted)" }}>Live PayPal Invoices</span>
              <span className="badge badge-sandbox">{stats.live_sandbox_count} LIVE</span>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <span style={{ fontSize: "0.8125rem", color: "var(--text-muted)" }}>Benchmark Demo Invoices</span>
              <span className="badge badge-demo">{stats.demo_count} DEMO</span>
            </div>
          </div>
        </div>

        {/* Recent Activity Audit Trail */}
        <div className="card">
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1rem" }}>
            <h3 style={{ fontSize: "0.9375rem", fontWeight: 600, color: "var(--text-main)" }}>
              Recent Audit Activity
            </h3>
            <span style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>Verified backend events</span>
          </div>

          {stats.recent_activity.length === 0 ? (
            <div style={{ padding: "1.5rem", textAlign: "center", color: "var(--text-muted)", fontSize: "0.8125rem" }}>
              No recent audit activity recorded yet.
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: "0.625rem", maxHeight: "240px", overflowY: "auto" }}>
              {stats.recent_activity.slice(0, 5).map((log) => (
                <div
                  key={log.id}
                  style={{
                    padding: "0.5rem 0.75rem",
                    backgroundColor: "var(--bg-subtle)",
                    borderRadius: "6px",
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    fontSize: "0.8125rem"
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                    <Clock size={14} color="var(--text-muted)" />
                    <div>
                      <span
                        onClick={() => onSelectInvoice(log.invoice_id)}
                        style={{ fontWeight: 600, color: "var(--primary)", cursor: "pointer", textDecoration: "underline" }}
                      >
                        {log.invoice_id}
                      </span>
                      <span style={{ marginLeft: "0.5rem", color: "var(--text-muted)", fontSize: "0.75rem" }}>
                        {log.action_type.replace(/_/g, " ")}
                      </span>
                    </div>
                  </div>
                  <span className={`badge ${log.status === "verified" || log.status === "success" ? "badge-low" : "badge-medium"}`}>
                    {log.status}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

