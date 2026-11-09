import React, { useState } from "react"
import { useAuth } from "./context/AuthContext"
import { Login } from "./components/Login"
import { CommandCenter } from "./components/CommandCenter"
import { RecoveryCenter } from "./components/RecoveryCenter"
import { InvoiceDetailView } from "./components/InvoiceDetail"
import { ReminderEditor } from "./components/ReminderEditor"
import { ActivityLogView } from "./components/ActivityLog"
import { AssistantPanel } from "./components/AssistantPanel"
import { PayPalBadge } from "./components/PayPalBadge"
import { APP_NAME, APP_TAGLINE } from "./config"
import { 
  ShieldCheck, 
  LayoutDashboard, 
  ListOrdered, 
  Clock, 
  Bot, 
  LogOut, 
  User
} from "lucide-react"

type ViewTab = "command" | "queue" | "detail" | "reminder" | "logs" | "assistant"

export const AppContent: React.FC = () => {
  const { isAuthenticated, user, logout } = useAuth()
  const [currentTab, setCurrentTab] = useState<ViewTab>("command")
  const [selectedInvoiceId, setSelectedInvoiceId] = useState<string | null>(null)

  if (!isAuthenticated) {
    return <Login />
  }

  const navigateToInvoice = (invId: string) => {
    setSelectedInvoiceId(invId)
    setCurrentTab("detail")
  }

  const navigateToReminder = (invId: string) => {
    setSelectedInvoiceId(invId)
    setCurrentTab("reminder")
  }

  return (
    <div style={{ minHeight: "100vh", display: "flex", flexDirection: "column" }}>
      {/* Top Navigation Bar */}
      <header style={{
        backgroundColor: "#ffffff",
        borderBottom: "1px solid var(--border-color)",
        position: "sticky",
        top: 0,
        zIndex: 50
      }}>
        <div style={{
          maxWidth: "1280px",
          margin: "0 auto",
          padding: "0.75rem 1.25rem",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          flexWrap: "wrap",
          gap: "1rem"
        }}>
          {/* Logo & Brand */}
          <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
            <div style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              width: "36px",
              height: "36px",
              borderRadius: "8px",
              backgroundColor: "var(--primary-light)",
              color: "var(--primary)"
            }}>
              <ShieldCheck size={22} />
            </div>
            <div>
              <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                <span style={{ fontSize: "1.125rem", fontWeight: 700, color: "var(--text-main)", letterSpacing: "-0.01em" }}>
                  {APP_NAME}
                </span>
                <span style={{ fontSize: "0.6875rem", backgroundColor: "var(--bg-subtle)", padding: "0.1rem 0.4rem", borderRadius: "4px", color: "var(--text-muted)" }}>
                  v2.0
                </span>
              </div>
              <div style={{ fontSize: "0.6875rem", color: "var(--text-muted)" }}>
                {APP_TAGLINE}
              </div>
            </div>
          </div>

          {/* Navigation Links */}
          <nav style={{ display: "flex", gap: "0.25rem" }}>
            <button
              className={currentTab === "command" ? "btn-primary btn-sm" : "btn-secondary btn-sm"}
              onClick={() => setCurrentTab("command")}
              style={{ display: "flex", alignItems: "center", gap: "0.375rem" }}
            >
              <LayoutDashboard size={14} />
              <span>Command Center</span>
            </button>

            <button
              className={currentTab === "queue" || currentTab === "detail" ? "btn-primary btn-sm" : "btn-secondary btn-sm"}
              onClick={() => setCurrentTab("queue")}
              style={{ display: "flex", alignItems: "center", gap: "0.375rem" }}
            >
              <ListOrdered size={14} />
              <span>Recovery Center</span>
            </button>

            <button
              className={currentTab === "logs" ? "btn-primary btn-sm" : "btn-secondary btn-sm"}
              onClick={() => setCurrentTab("logs")}
              style={{ display: "flex", alignItems: "center", gap: "0.375rem" }}
            >
              <Clock size={14} />
              <span>Activity Log</span>
            </button>

            <button
              className={currentTab === "assistant" ? "btn-primary btn-sm" : "btn-secondary btn-sm"}
              onClick={() => setCurrentTab("assistant")}
              style={{ display: "flex", alignItems: "center", gap: "0.375rem" }}
            >
              <Bot size={14} />
              <span>AI Assistant</span>
            </button>
          </nav>

          {/* Right: PayPal Badge & User */}
          <div style={{ display: "flex", alignItems: "center", gap: "1rem" }}>
            <PayPalBadge />

            <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
              <div style={{
                display: "flex",
                alignItems: "center",
                gap: "0.375rem",
                fontSize: "0.75rem",
                color: "var(--text-main)",
                backgroundColor: "var(--bg-subtle)",
                padding: "0.25rem 0.5rem",
                borderRadius: "6px"
              }}>
                <User size={13} color="var(--text-muted)" />
                <span>{user?.username}</span>
              </div>

              <button
                className="btn-secondary btn-sm"
                onClick={logout}
                title="Sign out of PayTriage"
                style={{ padding: "0.35rem 0.5rem" }}
              >
                <LogOut size={13} />
              </button>
            </div>
          </div>
        </div>
      </header>

      {/* Main Content Viewport */}
      <main style={{ flex: "1 1 auto", maxWidth: "1280px", width: "100%", margin: "0 auto", padding: "1.5rem" }}>
        {currentTab === "command" && (
          <CommandCenter
            onNavigateToQueue={() => setCurrentTab("queue")}
            onSelectInvoice={navigateToInvoice}
          />
        )}

        {currentTab === "queue" && (
          <RecoveryCenter
            onSelectInvoice={navigateToInvoice}
            selectedInvoiceId={selectedInvoiceId}
          />
        )}

        {currentTab === "detail" && selectedInvoiceId && (
          <InvoiceDetailView
            invoiceId={selectedInvoiceId}
            onBack={() => setCurrentTab("queue")}
            onDraftReminder={(id) => navigateToReminder(id)}
          />
        )}

        {currentTab === "reminder" && selectedInvoiceId && (
          <ReminderEditor
            invoiceId={selectedInvoiceId}
            onBack={() => setCurrentTab("detail")}
            onSuccessExecute={() => {
              setCurrentTab("logs")
            }}
          />
        )}

        {currentTab === "logs" && (
          <ActivityLogView
            onSelectInvoice={navigateToInvoice}
          />
        )}

        {currentTab === "assistant" && (
          <AssistantPanel
            onSelectInvoice={navigateToInvoice}
          />
        )}
      </main>
    </div>
  )
}

export function App() {
  return <AppContent />
}

export default App
