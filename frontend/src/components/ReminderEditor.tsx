import React, { useEffect, useState } from "react"
import { api, ApiError } from "../api/client"
import type { 
  ReminderDraft, 
  Tone, 
  ActionType, 
  ActionProposeResponse, 
  ActionApprovalResponse,
  ActionExecuteResponse,
  InvoiceDetail
} from "../api/types"
import { 
  ArrowLeft, 
  Copy, 
  Check, 
  Send, 
  ShieldCheck, 
  AlertTriangle, 
  RefreshCw,
  Lock
} from "lucide-react"

interface ReminderEditorProps {
  invoiceId: string
  onBack: () => void
  onSuccessExecute?: () => void
}

export const ReminderEditor: React.FC<ReminderEditorProps> = ({
  invoiceId,
  onBack,
  onSuccessExecute,
}) => {
  const [invoice, setInvoice] = useState<InvoiceDetail | null>(null)
  const [draft, setDraft] = useState<ReminderDraft | null>(null)
  const [loading, setLoading] = useState(true)
  const [generating, setGenerating] = useState(false)
  
  // Form State
  const [tone, setTone] = useState<Tone>("polite")
  const [subject, setSubject] = useState("")
  const [body, setBody] = useState("")
  const [copied, setCopied] = useState(false)

  // Selected Action for Approval
  const [actionType, setActionType] = useState<ActionType>("paypal_remind_invoice")

  // Approval Gate State
  const [approvalModalOpen, setApprovalModalOpen] = useState(false)
  const [proposal, setProposal] = useState<ActionProposeResponse | null>(null)
  const [approval, setApproval] = useState<ActionApprovalResponse | null>(null)
  const [execution, setExecution] = useState<ActionExecuteResponse | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const [processingAction, setProcessingAction] = useState(false)
  const [approvalInvalidated, setApprovalInvalidated] = useState(false)

  const loadInvoiceAndDraft = async () => {
    setLoading(true)
    try {
      const inv = await api.getInvoiceDetail(invoiceId)
      setInvoice(inv)

      // Choose default tone based on recommended action
      let defaultTone: Tone = "professional"
      if (inv.recommended_action === "polite_reminder") {
        defaultTone = "polite"
      } else if (inv.recommended_action === "firm_followup") {
        defaultTone = "firm"
      }
      setTone(defaultTone)

      // Set default action type
      if (inv.is_demo) {
        setActionType("record_copied_reminder")
      } else if (inv.status === "DRAFT") {
        setActionType("paypal_send_invoice")
      } else {
        setActionType("paypal_remind_invoice")
      }

      // Check existing drafts or generate fresh
      const existing = await api.getInvoiceReminders(invoiceId)
      if (existing.length > 0) {
        const latest = existing[0]
        setDraft(latest)
        setSubject(latest.subject)
        setBody(latest.body)
        setTone(latest.tone)
      } else {
        await handleGenerate(defaultTone)
      }
    } catch (err) {
      console.error("Load invoice error:", err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadInvoiceAndDraft()
  }, [invoiceId])

  const handleGenerate = async (selectedTone: Tone) => {
    setGenerating(true)
    setActionError(null)
    // If regenerating, invalidate any prior approval
    if (proposal) {
      setProposal(null)
      setApproval(null)
      setApprovalInvalidated(true)
    }

    try {
      const newDraft = await api.generateReminder(invoiceId, selectedTone)
      setDraft(newDraft)
      setSubject(newDraft.subject)
      setBody(newDraft.body)
      setTone(newDraft.tone)
    } catch (err) {
      if (err instanceof ApiError) {
        setActionError(err.detail)
      } else {
        setActionError("Failed to generate reminder draft.")
      }
    } finally {
      setGenerating(false)
    }
  }

  const handleContentChange = (newSubject: string, newBody: string) => {
    setSubject(newSubject)
    setBody(newBody)
    // If approved earlier, editing invalidates approval!
    if (proposal || approval) {
      setProposal(null)
      setApproval(null)
      setApprovalInvalidated(true)
    }
  }

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(`Subject: ${subject}\n\n${body}`)
      setCopied(true)
      setTimeout(() => setCopied(false), 2500)
      if (draft) {
        await api.copyReminder(draft.id)
      }
    } catch (err) {
      console.error("Copy error:", err)
    }
  }

  // Step 1: Propose Action
  const handleOpenApprovalModal = async () => {
    setProcessingAction(true)
    setActionError(null)
    setApprovalInvalidated(false)

    try {
      const params = {
        subject: subject.trim(),
        body: body.trim(),
        note: body.trim(),
        tone: tone,
      }
      const prop = await api.proposeAction(invoiceId, actionType, params)
      setProposal(prop)
      setApproval(null)
      setExecution(null)
      setApprovalModalOpen(true)
    } catch (err) {
      if (err instanceof ApiError) {
        setActionError(err.detail)
      } else {
        setActionError("Failed to propose action for approval.")
      }
    } finally {
      setProcessingAction(false)
    }
  }

  // Step 2: Approve Action
  const handleApprove = async () => {
    if (!proposal) return
    setProcessingAction(true)
    setActionError(null)

    try {
      const app = await api.approveAction(proposal.approval_id)
      setApproval(app)
    } catch (err) {
      if (err instanceof ApiError) {
        setActionError(err.detail)
      } else {
        setActionError("Failed to approve action.")
      }
    } finally {
      setProcessingAction(false)
    }
  }

  // Step 3: Execute Action
  const handleExecute = async () => {
    if (!proposal || !approval) return
    setProcessingAction(true)
    setActionError(null)

    try {
      const params = {
        subject: subject.trim(),
        body: body.trim(),
        note: body.trim(),
        tone: tone,
      }
      const exec = await api.executeAction(proposal.approval_id, actionType, params)
      setExecution(exec)
      if (onSuccessExecute) {
        onSuccessExecute()
      }
    } catch (err) {
      if (err instanceof ApiError) {
        setActionError(err.detail)
      } else {
        setActionError("Execution failed.")
      }
    } finally {
      setProcessingAction(false)
    }
  }

  if (loading) {
    return (
      <div className="card" style={{ textAlign: "center", padding: "4rem" }}>
        <div className="spinner" style={{ width: "2rem", height: "2rem", marginBottom: "0.75rem" }} />
        <div style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>
          Preparing payment reminder studio...
        </div>
      </div>
    )
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "1rem" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
          <button className="btn-secondary btn-sm" onClick={onBack}>
            <ArrowLeft size={14} style={{ marginRight: "0.25rem" }} />
            Back to Invoice
          </button>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
              <h2 style={{ fontSize: "1.25rem", fontWeight: 700, color: "var(--text-main)" }}>
                Payment Reminder & Action Approval Studio
              </h2>
              {invoice?.is_demo ? (
                <span className="badge badge-demo">DEMO DATA</span>
              ) : (
                <span className="badge badge-sandbox">LIVE SANDBOX</span>
              )}
            </div>
            <p style={{ fontSize: "0.8125rem", color: "var(--text-muted)" }}>
              Target: {invoice?.invoice_id} ({invoice?.customer_name}) • Outstanding: USD {invoice?.outstanding_amount}
            </p>
          </div>
        </div>

        {/* Action Type Selector */}
        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
          <span style={{ fontSize: "0.75rem", fontWeight: 600, color: "var(--text-muted)" }}>Action Target:</span>
          <select
            className="input"
            style={{ width: "auto", padding: "0.35rem 0.6rem" }}
            value={actionType}
            onChange={(e) => setActionType(e.target.value as ActionType)}
          >
            {invoice?.is_demo ? (
              <option value="record_copied_reminder">Record Copied Reminder (Demo Allowed)</option>
            ) : invoice?.status === "DRAFT" ? (
              <>
                <option value="paypal_send_invoice">PayPal Send Invoice (Draft Invoices)</option>
                <option value="record_copied_reminder">Record Copied Reminder (Manual Outreach)</option>
              </>
            ) : (
              <>
                <option value="paypal_remind_invoice">PayPal Remind Invoice (Live Sandbox)</option>
                <option value="record_copied_reminder">Record Copied Reminder (Manual Outreach)</option>
              </>
            )}
          </select>
        </div>
      </div>

      {/* Demo Warning Banner if Demo invoice */}
      {invoice?.is_demo && (
        <div style={{
          padding: "0.75rem 1rem",
          backgroundColor: "#f8fafc",
          border: "1px solid #cbd5e1",
          borderRadius: "6px",
          display: "flex",
          alignItems: "center",
          gap: "0.5rem",
          fontSize: "0.8125rem",
          color: "#475569"
        }}>
          <Lock size={16} color="#64748b" />
          <span>
            <strong>Demo Data Guard Active:</strong> Live PayPal API actions are restricted for demo benchmark invoices. You can generate, edit, copy, and approve manual copied reminders. Use a Live Sandbox invoice for live PayPal API actions.
          </span>
        </div>
      )}

      {/* Invalidation Alert */}
      {approvalInvalidated && (
        <div style={{
          padding: "0.75rem 1rem",
          backgroundColor: "#fff7ed",
          border: "1px solid #fed7aa",
          borderRadius: "6px",
          display: "flex",
          alignItems: "center",
          gap: "0.5rem",
          fontSize: "0.8125rem",
          color: "#c2410c"
        }}>
          <AlertTriangle size={16} />
          <span>
            <strong>Approval Invalidated:</strong> You edited the reminder content. For cryptographic integrity, you must re-propose and re-approve before executing.
          </span>
        </div>
      )}

      {actionError && (
        <div style={{
          padding: "0.75rem 1rem",
          backgroundColor: "var(--priority-critical-bg)",
          border: "1px solid var(--priority-critical-border)",
          borderRadius: "6px",
          color: "var(--priority-critical-text)",
          fontSize: "0.8125rem",
          display: "flex",
          alignItems: "center",
          gap: "0.5rem"
        }}>
          <AlertTriangle size={16} />
          <span>{actionError}</span>
        </div>
      )}

      {/* Reminder Editor Card */}
      <div className="card">
        {/* Controls: Tone Selector & Actions */}
        <div style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          flexWrap: "wrap",
          gap: "1rem",
          marginBottom: "1.25rem",
          paddingBottom: "1rem",
          borderBottom: "1px solid var(--border-color)"
        }}>
          {/* Tone Selector */}
          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
            <span style={{ fontSize: "0.8125rem", fontWeight: 600, color: "var(--text-main)" }}>
              Tone:
            </span>
            {(["polite", "friendly", "professional", "firm"] as Tone[]).map((t) => (
              <button
                key={t}
                type="button"
                className={tone === t ? "btn-primary btn-sm" : "btn-secondary btn-sm"}
                onClick={() => {
                  setTone(t)
                  handleGenerate(t)
                }}
                disabled={generating}
                style={{ textTransform: "capitalize" }}
              >
                {t}
              </button>
            ))}
          </div>

          {/* Buttons: Regenerate & Copy */}
          <div style={{ display: "flex", gap: "0.5rem" }}>
            <button
              className="btn-secondary btn-sm"
              onClick={() => handleGenerate(tone)}
              disabled={generating}
              style={{ display: "flex", alignItems: "center", gap: "0.25rem" }}
            >
              <RefreshCw size={13} className={generating ? "spinner" : ""} />
              <span>Regenerate Draft</span>
            </button>

            <button
              className="btn-secondary btn-sm"
              onClick={handleCopy}
              disabled={!subject || !body}
              style={{ display: "flex", alignItems: "center", gap: "0.25rem" }}
            >
              {copied ? <Check size={13} color="#16a34a" /> : <Copy size={13} />}
              <span>{copied ? "Copied!" : "Copy to Clipboard"}</span>
            </button>
          </div>
        </div>

        {/* Form Fields: Subject & Body */}
        <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
          <div>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.375rem" }}>
              <label style={{ fontSize: "0.8125rem", fontWeight: 600, color: "var(--text-main)" }}>
                Email Subject Line
              </label>
              <span style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
                Grounded with verified invoice number
              </span>
            </div>
            <input
              type="text"
              className="input"
              value={subject}
              onChange={(e) => handleContentChange(e.target.value, body)}
              placeholder="Notice regarding Invoice..."
            />
          </div>

          <div>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.375rem" }}>
              <label style={{ fontSize: "0.8125rem", fontWeight: 600, color: "var(--text-main)" }}>
                Reminder Message Body
              </label>
              <span style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
                Status: <strong>DRAFT ONLY</strong> (Never sent autonomously)
              </span>
            </div>
            <textarea
              className="input"
              rows={8}
              value={body}
              onChange={(e) => handleContentChange(subject, e.target.value)}
              placeholder="Enter reminder note..."
              style={{ resize: "vertical", lineHeight: 1.5 }}
            />
          </div>
        </div>

        {/* Submit to Approval Gate */}
        <div style={{
          marginTop: "1.5rem",
          paddingTop: "1rem",
          borderTop: "1px solid var(--border-color)",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          flexWrap: "wrap",
          gap: "1rem"
        }}>
          <div style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
            <ShieldCheck size={14} style={{ display: "inline", verticalAlign: "middle", marginRight: "0.25rem", color: "var(--primary)" }} />
            Human approval gate required prior to any execution. AI cannot execute.
          </div>

          <button
            className="btn-primary"
            onClick={handleOpenApprovalModal}
            disabled={!subject.trim() || !body.trim() || processingAction}
            style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}
          >
            <ShieldCheck size={16} />
            <span>Propose & Open Approval Dialog</span>
          </button>
        </div>
      </div>

      {/* APPROVAL DIALOG / MODAL */}
      {approvalModalOpen && proposal && (
        <div style={{
          position: "fixed",
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          backgroundColor: "rgba(15, 23, 42, 0.6)",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          padding: "1rem",
          zIndex: 9999
        }}>
          <div className="card" style={{ maxWidth: "560px", width: "100%", maxHeight: "90vh", overflowY: "auto", padding: "1.75rem" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "1rem" }}>
              <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                <ShieldCheck size={24} color="var(--primary)" />
                <div>
                  <h3 style={{ fontSize: "1.125rem", fontWeight: 700, color: "var(--text-main)" }}>
                    Human Action Approval Gate
                  </h3>
                  <p style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
                    Cryptographic SHA-256 integrity verification
                  </p>
                </div>
              </div>
              <button
                className="btn-secondary btn-sm"
                onClick={() => setApprovalModalOpen(false)}
                disabled={processingAction}
              >
                Close
              </button>
            </div>

            {/* Approval Details Table */}
            <div style={{
              backgroundColor: "var(--bg-subtle)",
              border: "1px solid var(--border-color)",
              borderRadius: "6px",
              padding: "0.875rem",
              marginBottom: "1rem",
              fontSize: "0.8125rem",
              display: "flex",
              flexDirection: "column",
              gap: "0.5rem"
            }}>
              <div style={{ display: "flex", justifyContent: "space-between" }}>
                <span style={{ color: "var(--text-muted)" }}>Approval ID:</span>
                <span style={{ fontWeight: 600, fontFamily: "monospace" }}>{proposal.approval_id}</span>
              </div>
              <div style={{ display: "flex", justifyContent: "space-between" }}>
                <span style={{ color: "var(--text-muted)" }}>Invoice ID:</span>
                <span style={{ fontWeight: 600 }}>{proposal.invoice_id}</span>
              </div>
              <div style={{ display: "flex", justifyContent: "space-between" }}>
                <span style={{ color: "var(--text-muted)" }}>Action Type:</span>
                <span className="badge badge-sandbox">{proposal.action_type}</span>
              </div>
              <div style={{ display: "flex", justifyContent: "space-between" }}>
                <span style={{ color: "var(--text-muted)" }}>Current Status:</span>
                <span className={`badge ${approval ? "badge-low" : "badge-medium"}`}>
                  {execution ? execution.status : approval ? approval.status : proposal.status}
                </span>
              </div>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span style={{ color: "var(--text-muted)" }}>SHA-256 Hash:</span>
                <span style={{ fontFamily: "monospace", fontSize: "0.75rem", color: "var(--primary)" }}>
                  {proposal.hash.substring(0, 16)}...{proposal.hash.substring(48)}
                </span>
              </div>
              <div style={{ display: "flex", justifyContent: "space-between" }}>
                <span style={{ color: "var(--text-muted)" }}>Expires At:</span>
                <span style={{ fontSize: "0.75rem" }}>{proposal.expires_at}</span>
              </div>
            </div>

            {/* Exact Parameters Preview */}
            <div style={{ marginBottom: "1rem" }}>
              <div style={{ fontSize: "0.75rem", fontWeight: 600, color: "var(--text-muted)", marginBottom: "0.375rem" }}>
                EXACT VERIFIED ACTION PARAMETERS:
              </div>
              <div style={{
                backgroundColor: "#ffffff",
                border: "1px solid var(--border-color)",
                borderRadius: "6px",
                padding: "0.75rem",
                fontSize: "0.8125rem"
              }}>
                <div><strong>Subject:</strong> {subject}</div>
                <div style={{ marginTop: "0.375rem" }}><strong>Message Note:</strong></div>
                <div style={{
                  color: "var(--text-muted)",
                  marginTop: "0.25rem",
                  whiteSpace: "pre-wrap",
                  fontSize: "0.75rem",
                  maxHeight: "100px",
                  overflowY: "auto"
                }}>
                  {body}
                </div>
              </div>
            </div>

            {/* Warning regarding edits */}
            <div style={{
              fontSize: "0.75rem",
              color: "#b45309",
              backgroundColor: "#fffbeb",
              border: "1px solid #fde68a",
              padding: "0.5rem 0.75rem",
              borderRadius: "6px",
              marginBottom: "1.25rem"
            }}>
              <strong>Tamper Protection:</strong> If parameters are modified after approval, the SHA-256 hash recomputation will fail with HTTP 409 Conflict.
            </div>

            {/* Execution Result Box (if executed) */}
            {execution && (
              <div style={{
                padding: "0.875rem",
                backgroundColor: execution.verified ? "#ecfdf5" : "#fef2f2",
                border: `1px solid ${execution.verified ? "#a7f3d0" : "#fecaca"}`,
                borderRadius: "6px",
                marginBottom: "1rem",
                fontSize: "0.8125rem"
              }}>
                <div style={{ fontWeight: 700, color: execution.verified ? "#065f46" : "#991b1b" }}>
                  {execution.verified ? "Action Executed & Verified with PayPal!" : "Execution Reported Failure"}
                </div>
                <div style={{ marginTop: "0.25rem", color: "var(--text-main)" }}>
                  {execution.message}
                </div>
              </div>
            )}

            {/* Modal Action Buttons */}
            <div style={{ display: "flex", justifyContent: "flex-end", gap: "0.75rem" }}>
              {!approval && !execution && (
                <button
                  className="btn-primary"
                  onClick={handleApprove}
                  disabled={processingAction}
                  style={{ display: "flex", alignItems: "center", gap: "0.375rem" }}
                >
                  {processingAction ? <span className="spinner" /> : <ShieldCheck size={16} />}
                  <span>Approve Action as Merchant</span>
                </button>
              )}

              {approval && !execution && (
                <button
                  className="btn-primary"
                  onClick={handleExecute}
                  disabled={processingAction}
                  style={{
                    backgroundColor: "#16a34a",
                    display: "flex",
                    alignItems: "center",
                    gap: "0.375rem"
                  }}
                >
                  {processingAction ? <span className="spinner" /> : <Send size={16} />}
                  <span>Execute Approved Action Now</span>
                </button>
              )}

              {execution && (
                <button
                  className="btn-primary"
                  onClick={() => {
                    setApprovalModalOpen(false)
                    if (onSuccessExecute) onSuccessExecute()
                  }}
                >
                  Done
                </button>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

