import React, { useState } from "react"
import { api, ApiError } from "../api/client"
import { 
  Bot, 
  Send, 
  Sparkles, 
  User, 
  ShieldCheck, 
  CornerDownRight,
  ExternalLink
} from "lucide-react"

interface Message {
  id: string
  role: "user" | "assistant"
  text: string
  intent?: string
  referencedInvoices?: string[]
  suggestions?: string[]
}

interface AssistantPanelProps {
  onSelectInvoice: (invoiceId: string) => void
}

export const AssistantPanel: React.FC<AssistantPanelProps> = ({ onSelectInvoice }) => {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: "init",
      role: "assistant",
      text: "Hello! I am your PayTriage Recovery Intelligence Assistant. I can analyze overdue portfolios, explain scoring rationale, identify high-priority invoices, and draft customized reminder copy grounded in verified facts.",
      suggestions: [
        "Which invoices should I follow up on today?",
        "Why is INV-SEV-009 our highest recovery priority?",
        "Show me all invoices overdue by more than 14 days",
      ]
    }
  ])
  const [inputQuery, setInputQuery] = useState("")
  const [loading, setLoading] = useState(false)

  // 5 benchmark example chips as requested by spec
  const EXAMPLE_PROMPTS = [
    "Which invoices should I follow up on today?",
    "Why is INV-SEV-009 our highest recovery priority?",
    "Draft a polite reminder for INV-NEW-006",
    "Show me all invoices overdue by more than 14 days",
    "Which recovery actions are pending approval?",
  ]

  const handleSend = async (queryText: string) => {
    const q = queryText.trim()
    if (!q || loading) return

    const userMsg: Message = {
      id: `u-${Date.now()}`,
      role: "user",
      text: q,
    }
    setMessages((prev) => [...prev, userMsg])
    setInputQuery("")
    setLoading(true)

    try {
      const res = await api.askAssistant(q)
      const assistantMsg: Message = {
        id: `a-${Date.now()}`,
        role: "assistant",
        text: res.answer,
        intent: res.intent,
        referencedInvoices: res.referenced_invoice_ids,
        suggestions: res.actionable_suggestions,
      }
      setMessages((prev) => [...prev, assistantMsg])
    } catch (err) {
      const errMsg: Message = {
        id: `err-${Date.now()}`,
        role: "assistant",
        text: err instanceof ApiError ? `Error: ${err.detail}` : "Sorry, I encountered an issue contacting the assistant service.",
      }
      setMessages((prev) => [...prev, errMsg])
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1rem", height: "100%" }}>
      {/* Header */}
      <div>
        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
          <Sparkles size={20} color="var(--primary)" />
          <h2 style={{ fontSize: "1.25rem", fontWeight: 700, color: "var(--text-main)" }}>
            Recovery Intelligence Assistant
          </h2>
        </div>
        <p style={{ fontSize: "0.8125rem", color: "var(--text-muted)" }}>
          Ask natural-language questions about receivables aging, scoring factors, and next-best actions.
        </p>
      </div>

      {/* 5 Example Prompt Chips */}
      <div className="card" style={{ padding: "0.75rem 1rem" }}>
        <div style={{ fontSize: "0.75rem", fontWeight: 600, color: "var(--text-muted)", marginBottom: "0.5rem" }}>
          EXAMPLE QUERIES (CLICK TO RUN):
        </div>
        <div style={{ display: "flex", flexWrap: "wrap", gap: "0.375rem" }}>
          {EXAMPLE_PROMPTS.map((prompt, idx) => (
            <button
              key={idx}
              className="btn-secondary btn-sm"
              onClick={() => handleSend(prompt)}
              disabled={loading}
              style={{
                fontSize: "0.75rem",
                padding: "0.25rem 0.625rem",
                textAlign: "left",
                backgroundColor: "var(--bg-app)"
              }}
            >
              {prompt}
            </button>
          ))}
        </div>
      </div>

      {/* Chat Messages Log */}
      <div className="card" style={{
        flex: "1 1 auto",
        minHeight: "360px",
        maxHeight: "500px",
        overflowY: "auto",
        display: "flex",
        flexDirection: "column",
        gap: "1rem",
        padding: "1.25rem"
      }}>
        {messages.map((msg) => (
          <div
            key={msg.id}
            style={{
              display: "flex",
              gap: "0.75rem",
              alignItems: "flex-start",
              alignSelf: msg.role === "user" ? "flex-end" : "flex-start",
              maxWidth: "85%"
            }}
          >
            {msg.role === "assistant" && (
              <div style={{
                width: "28px",
                height: "28px",
                borderRadius: "50%",
                backgroundColor: "var(--primary-light)",
                color: "var(--primary)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                flexShrink: 0
              }}>
                <Bot size={16} />
              </div>
            )}

            <div style={{
              backgroundColor: msg.role === "user" ? "var(--primary)" : "var(--bg-subtle)",
              color: msg.role === "user" ? "#ffffff" : "var(--text-main)",
              padding: "0.75rem 1rem",
              borderRadius: "8px",
              fontSize: "0.8125rem",
              lineHeight: 1.5,
              whiteSpace: "pre-wrap"
            }}>
              {msg.text}

              {/* Referenced invoice chips */}
              {msg.referencedInvoices && msg.referencedInvoices.length > 0 && (
                <div style={{ marginTop: "0.5rem", paddingTop: "0.5rem", borderTop: "1px solid rgba(0,0,0,0.1)" }}>
                  <span style={{ fontSize: "0.75rem", fontWeight: 600, opacity: 0.85, marginRight: "0.375rem" }}>
                    Referenced Invoices:
                  </span>
                  <div style={{ display: "inline-flex", flexWrap: "wrap", gap: "0.25rem", marginTop: "0.25rem" }}>
                    {msg.referencedInvoices.map((invId) => (
                      <button
                        key={invId}
                        className="btn-secondary btn-sm"
                        style={{ fontSize: "0.6875rem", padding: "0.1rem 0.4rem" }}
                        onClick={() => onSelectInvoice(invId)}
                      >
                        {invId} <ExternalLink size={10} style={{ marginLeft: "0.2rem" }} />
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {/* Actionable suggestions */}
              {msg.suggestions && msg.suggestions.length > 0 && (
                <div style={{ marginTop: "0.5rem", display: "flex", flexWrap: "wrap", gap: "0.25rem" }}>
                  {msg.suggestions.map((sug, i) => (
                    <button
                      key={i}
                      className="btn-secondary btn-sm"
                      style={{ fontSize: "0.6875rem", padding: "0.15rem 0.4rem" }}
                      onClick={() => handleSend(sug)}
                    >
                      <CornerDownRight size={10} style={{ marginRight: "0.2rem" }} />
                      {sug}
                    </button>
                  ))}
                </div>
              )}
            </div>

            {msg.role === "user" && (
              <div style={{
                width: "28px",
                height: "28px",
                borderRadius: "50%",
                backgroundColor: "var(--border-color)",
                color: "var(--text-main)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                flexShrink: 0
              }}>
                <User size={16} />
              </div>
            )}
          </div>
        ))}

        {loading && (
          <div style={{ display: "flex", gap: "0.75rem", alignItems: "center" }}>
            <div style={{
              width: "28px",
              height: "28px",
              borderRadius: "50%",
              backgroundColor: "var(--primary-light)",
              color: "var(--primary)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center"
            }}>
              <Bot size={16} />
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: "0.375rem", color: "var(--text-muted)", fontSize: "0.8125rem" }}>
              <span className="spinner" />
              <span>Analyzing portfolio data...</span>
            </div>
          </div>
        )}
      </div>

      {/* Query Input Box */}
      <form
        onSubmit={(e) => {
          e.preventDefault()
          handleSend(inputQuery)
        }}
        style={{ display: "flex", gap: "0.5rem" }}
      >
        <input
          type="text"
          className="input"
          placeholder="Ask a question about overdue accounts or recovery recommendations..."
          value={inputQuery}
          onChange={(e) => setInputQuery(e.target.value)}
          disabled={loading}
        />
        <button
          type="submit"
          className="btn-primary"
          disabled={loading || !inputQuery.trim()}
          style={{ display: "flex", alignItems: "center", gap: "0.375rem", padding: "0.5rem 1.25rem" }}
        >
          <Send size={15} />
          <span>Ask</span>
        </button>
      </form>

      <div style={{ fontSize: "0.6875rem", color: "var(--text-muted)", textAlign: "center" }}>
        <ShieldCheck size={12} style={{ display: "inline", verticalAlign: "middle", marginRight: "0.25rem" }} />
        AI provides advisory decision support based on verified facts. Autonomous execution is strictly blocked.
      </div>
    </div>
  )
}

