import React, { useEffect, useState } from "react"
import { api, ApiError } from "../api/client"
import type { InvoiceDetail, StrategyComparison, ExplanationResponse } from "../api/types"
import { 
  ArrowLeft, 
  Sparkles, 
  AlertTriangle, 
  Send, 
  Layers,
  ChevronDown,
  ChevronUp
} from "lucide-react"

interface InvoiceDetailViewProps {
  invoiceId: string
  onBack: () => void
  onDraftReminder: (invoiceId: string, recommendedTone?: string) => void
}

export const InvoiceDetailView: React.FC<InvoiceDetailViewProps> = ({
  invoiceId,
  onBack,
  onDraftReminder,
}) => {
  const [detail, setDetail] = useState<InvoiceDetail | null>(null)
  const [strategies, setStrategies] = useState<StrategyComparison | null>(null)
  const [explanation, setExplanation] = useState<ExplanationResponse | null>(null)
  
  const [loading, setLoading] = useState(true)
  const [explaining, setExplaining] = useState(false)
  const [customQuestion, setCustomQuestion] = useState("")
  const [error, setError] = useState<string | null>(null)
  const [showAllStrategies, setShowAllStrategies] = useState(false)

  const loadData = async () => {
    setLoading(true)
    setError(null)
    try {
      const [detailData, stratData] = await Promise.all([
        api.getInvoiceDetail(invoiceId),
        api.getInvoiceStrategies(invoiceId),
      ])
      setDetail(detailData)
      setStrategies(stratData)
      
      // Auto-fetch explanation
      generateExplanation()
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.detail)
      } else {
        setError("Failed to load invoice diagnostic details.")
      }
    } finally {
      setLoading(false)
    }
  }

  const generateExplanation = async (question?: string) => {
    setExplaining(true)
    try {
      const exp = await api.explainInvoice(invoiceId, question)
      setExplanation(exp)
    } catch (err) {
      console.error("Explanation error:", err)
    } finally {
      setExplaining(false)
    }
  }

  useEffect(() => {
    loadData()
  }, [invoiceId])

  const handleQuestionSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (customQuestion.trim()) {
      generateExplanation(customQuestion.trim())
    }
  }

  if (loading) {
    return (
      <div className="card" style={{ textAlign: "center", padding: "4rem" }}>
        <div className="spinner" style={{ width: "2rem", height: "2rem", marginBottom: "0.75rem" }} />
        <div style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>
          Evaluating invoice recovery scoring breakdown...
        </div>
      </div>
    )
  }

  if (error || !detail) {
    return (
      <div className="card" style={{ padding: "2rem", textAlign: "center" }}>
        <AlertTriangle size={36} color="var(--priority-critical-text)" style={{ marginBottom: "0.75rem" }} />
        <h3 style={{ fontSize: "1.125rem", color: "var(--text-main)" }}>Failed to Load Invoice Details</h3>
        <p style={{ color: "var(--text-muted)", fontSize: "0.875rem", margin: "0.5rem 0 1rem" }}>
          {error || "Invoice not found."}
        </p>
        <button className="btn-secondary" onClick={onBack}>
          <ArrowLeft size={14} style={{ marginRight: "0.375rem" }} />
          Back to Queue
        </button>
      </div>
    )
  }

  const getPriorityBadge = (p: string) => {
    switch (p) {
      case "CRITICAL": return "badge-critical"
      case "HIGH": return "badge-high"
      case "MEDIUM": return "badge-medium"
      default: return "badge-low"
    }
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
      {/* Navigation & Header */}
      <div style={{
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
        flexWrap: "wrap",
        gap: "1rem"
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
          <button className="btn-secondary btn-sm" onClick={onBack}>
            <ArrowLeft size={14} style={{ marginRight: "0.25rem" }} />
            Back
          </button>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
              <h2 style={{ fontSize: "1.25rem", fontWeight: 700, color: "var(--text-main)" }}>
                {detail.invoice_id}
              </h2>
              <span className={`badge ${getPriorityBadge(detail.priority)}`}>
                {detail.priority} (Score {detail.score})
              </span>
              {detail.is_demo ? (
                <span className="badge badge-demo">DEMO DATA</span>
              ) : (
                <span className="badge badge-sandbox">LIVE SANDBOX</span>
              )}
            </div>
            <p style={{ fontSize: "0.8125rem", color: "var(--text-muted)" }}>
              {detail.customer_name} • Due: {detail.due_date} ({detail.days_overdue > 0 ? `${detail.days_overdue} days overdue` : "Due soon"})
            </p>
          </div>
        </div>

        <button
          className="btn-primary"
          onClick={() => onDraftReminder(detail.invoice_id)}
          style={{ display: "flex", alignItems: "center", gap: "0.375rem" }}
        >
          <Send size={14} />
          <span>Prepare Payment Reminder Draft</span>
        </button>
      </div>

      {/* Assumption Warning Banner if history missing */}
      {detail.has_assumption_flag && (
        <div style={{
          padding: "0.875rem 1rem",
          backgroundColor: "#fffbeb",
          border: "1px solid #fde68a",
          borderRadius: "8px",
          display: "flex",
          alignItems: "flex-start",
          gap: "0.75rem",
          color: "#92400e"
        }}>
          <AlertTriangle size={18} style={{ flexShrink: 0, marginTop: "0.125rem" }} />
          <div>
            <div style={{ fontWeight: 600, fontSize: "0.875rem" }}>
              Assumption Applied: Missing Customer Payment History
            </div>
            <div style={{ fontSize: "0.8125rem", marginTop: "0.125rem", opacity: 0.9 }}>
              {detail.assumption_reason || "Customer payment history is not on record. The scoring engine assigned neutral points (4 pts) under conservative assumption rules without fabricating payment track records."}
            </div>
          </div>
        </div>
      )}

      {/* Grid: Factor Breakdown + AI Explanation */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(360px, 1fr))", gap: "1.25rem" }}>
        {/* Score Breakdown Card */}
        <div className="card">
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1rem" }}>
            <div>
              <h3 style={{ fontSize: "1rem", fontWeight: 700, color: "var(--text-main)" }}>
                Recovery Score Breakdown
              </h3>
              <p style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
                Deterministic point allocation totaling {detail.score}/100
              </p>
            </div>
            <div style={{
              width: "48px",
              height: "48px",
              borderRadius: "50%",
              backgroundColor: "var(--primary-light)",
              color: "var(--primary)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              fontWeight: 800,
              fontSize: "1.125rem"
            }}>
              {detail.score}
            </div>
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
            {detail.contributing_factors.map((factor, idx) => (
              <div
                key={idx}
                style={{
                  padding: "0.625rem 0.75rem",
                  border: "1px solid var(--border-color)",
                  borderRadius: "6px",
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center"
                }}
              >
                <div>
                  <div style={{ fontWeight: 600, fontSize: "0.8125rem", color: "var(--text-main)" }}>
                    {factor.factor_name.replace(/_/g, " ")}
                  </div>
                  <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginTop: "0.125rem" }}>
                    {factor.description}
                  </div>
                </div>
                <div style={{
                  fontWeight: 700,
                  fontSize: "0.875rem",
                  color: factor.points > 0 ? "var(--primary)" : "var(--text-muted)",
                  paddingLeft: "0.75rem"
                }}>
                  +{factor.points}
                </div>
              </div>
            ))}
          </div>

          {/* Unavailable data notices */}
          {detail.unavailable_data_points.length > 0 && (
            <div style={{ marginTop: "1rem", paddingTop: "0.75rem", borderTop: "1px solid var(--border-color)" }}>
              <div style={{ fontSize: "0.75rem", fontWeight: 600, color: "var(--text-muted)", marginBottom: "0.375rem" }}>
                UNAVAILABLE DATA POINTS (NO POINTS ASSIGNED):
              </div>
              <ul style={{ paddingLeft: "1.25rem", fontSize: "0.75rem", color: "var(--text-muted)" }}>
                {detail.unavailable_data_points.map((pt, i) => (
                  <li key={i}>{pt}</li>
                ))}
              </ul>
            </div>
          )}
        </div>

        {/* Grounded AI Explanation Card */}
        <div className="card">
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "0.75rem" }}>
            <div>
              <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                <Sparkles size={18} color="var(--primary)" />
                <h3 style={{ fontSize: "1rem", fontWeight: 700, color: "var(--text-main)" }}>
                  Grounded Recovery Explanation
                </h3>
              </div>
              <p style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginTop: "0.125rem" }}>
                Factually grounded in backend calculations; protected against hallucinations.
              </p>
            </div>

            {explanation && (
              <span className={`badge ${explanation.source === "ai" ? "badge-sandbox" : "badge-medium"}`}>
                {explanation.source === "ai"
                  ? "AI-generated"
                  : `Generated without AI (${explanation.fallback_reason || "deterministic"})`}
              </span>
            )}
          </div>

          {explaining ? (
            <div style={{ textAlign: "center", padding: "2.5rem" }}>
              <div className="spinner" style={{ width: "1.5rem", height: "1.5rem", marginBottom: "0.5rem" }} />
              <div style={{ fontSize: "0.8125rem", color: "var(--text-muted)" }}>
                Synthesizing grounded explanation...
              </div>
            </div>
          ) : explanation ? (
            <div style={{ display: "flex", flexDirection: "column", gap: "0.875rem" }}>
              {/* Summary */}
              <div style={{
                padding: "0.75rem",
                backgroundColor: "var(--bg-subtle)",
                borderRadius: "6px",
                fontSize: "0.8125rem",
                color: "var(--text-main)",
                lineHeight: 1.5
              }}>
                {explanation.summary}
              </div>

              {/* Key Factors */}
              <div>
                <div style={{ fontSize: "0.75rem", fontWeight: 600, color: "var(--text-muted)", marginBottom: "0.375rem" }}>
                  KEY DRIVING FACTORS:
                </div>
                <ul style={{ paddingLeft: "1.25rem", fontSize: "0.8125rem", color: "var(--text-main)", display: "flex", flexDirection: "column", gap: "0.25rem" }}>
                  {explanation.key_factors.map((f, i) => (
                    <li key={i}>{f}</li>
                  ))}
                </ul>
              </div>

              {/* Recommended Action */}
              <div style={{
                padding: "0.625rem 0.75rem",
                border: "1px solid var(--primary-border)",
                backgroundColor: "var(--primary-light)",
                borderRadius: "6px",
                fontSize: "0.8125rem"
              }}>
                <span style={{ fontWeight: 600, color: "var(--primary)" }}>Recommended Action: </span>
                <span style={{ color: "var(--text-main)" }}>{explanation.recommended_action}</span>
              </div>

              {/* Confidence note / caveats */}
              <div style={{ fontSize: "0.6875rem", color: "var(--text-muted)", fontStyle: "italic" }}>
                {explanation.confidence_note}
              </div>

              {/* Optional Question Box */}
              <form onSubmit={handleQuestionSubmit} style={{ marginTop: "0.5rem" }}>
                <label style={{ display: "block", fontSize: "0.75rem", fontWeight: 600, color: "var(--text-main)", marginBottom: "0.25rem" }}>
                  Ask a Question About This Invoice
                </label>
                <div style={{ display: "flex", gap: "0.5rem" }}>
                  <input
                    type="text"
                    className="input"
                    value={customQuestion}
                    onChange={(e) => setCustomQuestion(e.target.value)}
                    placeholder="e.g. Why is this invoice prioritized higher than others?"
                    style={{ fontSize: "0.75rem" }}
                  />
                  <button type="submit" className="btn-secondary btn-sm" disabled={explaining || !customQuestion.trim()}>
                    Ask
                  </button>
                </div>
              </form>
            </div>
          ) : (
            <div style={{ textAlign: "center", padding: "1.5rem" }}>
              <button className="btn-secondary btn-sm" onClick={() => generateExplanation()}>
                Generate Grounded Explanation
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Recovery Strategies Comparison */}
      {strategies && (
        <div className="card">
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1rem" }}>
            <div>
              <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                <Layers size={18} color="var(--primary)" />
                <h3 style={{ fontSize: "1rem", fontWeight: 700, color: "var(--text-main)" }}>
                  Multi-Strategy Recovery Comparison
                </h3>
              </div>
              <p style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginTop: "0.125rem" }}>
                {strategies.reason}
              </p>
            </div>
            <button
              className="btn-secondary btn-sm"
              onClick={() => setShowAllStrategies(!showAllStrategies)}
              style={{ display: "flex", alignItems: "center", gap: "0.25rem" }}
            >
              <span>{showAllStrategies ? "Show Recommended Only" : "Compare All Strategies"}</span>
              {showAllStrategies ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
            </button>
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: "1rem" }}>
            {strategies.strategies
              .filter((s) => showAllStrategies || s.classification === "recommended")
              .map((strat) => (
                <div
                  key={strat.strategy_id}
                  style={{
                    padding: "1rem",
                    borderRadius: "6px",
                    border: strat.classification === "recommended"
                      ? "2px solid var(--primary)"
                      : "1px solid var(--border-color)",
                    backgroundColor: strat.classification === "recommended"
                      ? "var(--primary-light)"
                      : "var(--bg-card)"
                  }}
                >
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.5rem" }}>
                    <div style={{ fontWeight: 700, fontSize: "0.875rem", color: "var(--text-main)" }}>
                      {strat.name}
                    </div>
                    <span className={`badge ${
                      strat.classification === "recommended"
                        ? "badge-low"
                        : strat.classification === "alternative"
                        ? "badge-medium"
                        : "badge-demo"
                    }`}>
                      {strat.classification}
                    </span>
                  </div>

                  <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginBottom: "0.5rem" }}>
                    Timing: {strat.recommended_timing} • Tone: {strat.tone}
                  </div>

                  <div style={{ fontSize: "0.8125rem", marginBottom: "0.5rem" }}>
                    <div style={{ fontWeight: 600, color: "#166534" }}>Advantages:</div>
                    <div style={{ color: "var(--text-main)" }}>{strat.advantages}</div>
                  </div>

                  <div style={{ fontSize: "0.8125rem" }}>
                    <div style={{ fontWeight: 600, color: "#991b1b" }}>Limitations:</div>
                    <div style={{ color: "var(--text-muted)" }}>{strat.limitations}</div>
                  </div>
                </div>
              ))}
          </div>
        </div>
      )}
    </div>
  )
}

