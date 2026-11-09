import React, { useEffect, useState } from "react"
import { api } from "../api/client"
import type { PayPalStatus } from "../api/types"
import { CheckCircle2, AlertTriangle, RefreshCw } from "lucide-react"

export const PayPalBadge: React.FC = () => {
  const [status, setStatus] = useState<PayPalStatus | null>(null)
  const [loading, setLoading] = useState(true)

  const fetchStatus = async () => {
    setLoading(true)
    try {
      const data = await api.getPayPalStatus()
      setStatus(data)
    } catch {
      setStatus(null)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchStatus()
  }, [])

  if (loading) {
    return (
      <div style={{ display: "inline-flex", alignItems: "center", gap: "0.375rem", fontSize: "0.75rem", color: "var(--text-muted)" }}>
        <span className="spinner" style={{ width: "0.75rem", height: "0.75rem" }} />
        <span>Checking PayPal...</span>
      </div>
    )
  }

  if (!status || !status.configured) {
    return (
      <div
        title={status?.message || "PayPal Sandbox credentials missing in backend/.env"}
        style={{
          display: "inline-flex",
          alignItems: "center",
          gap: "0.375rem",
          padding: "0.25rem 0.625rem",
          backgroundColor: "#fff1f2",
          border: "1px solid #fecdd3",
          borderRadius: "9999px",
          color: "#be123c",
          fontSize: "0.75rem",
          fontWeight: 600
        }}
      >
        <AlertTriangle size={13} />
        <span>Sandbox Not Configured</span>
        <button
          onClick={fetchStatus}
          title="Refresh status"
          style={{ background: "none", border: "none", color: "#be123c", padding: 0, marginLeft: "0.25rem" }}
        >
          <RefreshCw size={11} />
        </button>
      </div>
    )
  }

  return (
    <div
      title={`PayPal Sandbox Mode: ${status.mode} (${status.client_id_preview})`}
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: "0.375rem",
        padding: "0.25rem 0.625rem",
        backgroundColor: "#ecfdf5",
        border: "1px solid #a7f3d0",
        borderRadius: "9999px",
        color: "#047857",
        fontSize: "0.75rem",
        fontWeight: 600
      }}
    >
      <CheckCircle2 size={13} />
      <span>PayPal Sandbox Connected</span>
      <span style={{ fontSize: "0.6875rem", opacity: 0.8, fontWeight: 400 }}>({status.client_id_preview})</span>
      <button
        onClick={fetchStatus}
        title="Refresh status"
        style={{ background: "none", border: "none", color: "#047857", padding: 0, marginLeft: "0.25rem" }}
      >
        <RefreshCw size={11} />
      </button>
    </div>
  )
}

