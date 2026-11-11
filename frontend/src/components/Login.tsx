import React, { useState } from "react"
import { api, ApiError } from "../api/client"
import { useAuth } from "../context/AuthContext"
import { APP_NAME, APP_TAGLINE } from "../config"
import { ShieldCheck, LogIn, AlertCircle } from "lucide-react"

export const Login: React.FC = () => {
  const { login } = useAuth()
  const [username, setUsername] = useState("")
  const [password, setPassword] = useState("")
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setError(null)

    try {
      const res = await api.login(username, password)
      login(res.access_token, res.user)
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.detail)
      } else {
        setError("Login failed. Please check your credentials or connection.")
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{
      minHeight: "100vh",
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      backgroundColor: "var(--bg-app)",
      padding: "1.5rem"
    }}>
      <div className="card" style={{ maxWidth: "420px", width: "100%", padding: "2rem" }}>
        <div style={{ textAlign: "center", marginBottom: "1.5rem" }}>
          <div style={{
            display: "inline-flex",
            alignItems: "center",
            justifyContent: "center",
            width: "48px",
            height: "48px",
            borderRadius: "12px",
            backgroundColor: "var(--primary-light)",
            color: "var(--primary)",
            marginBottom: "0.75rem"
          }}>
            <ShieldCheck size={28} />
          </div>
          <h1 style={{ fontSize: "1.5rem", fontWeight: 700, color: "var(--text-main)" }}>
            {APP_NAME}
          </h1>
          <p style={{ fontSize: "0.875rem", color: "var(--text-muted)", marginTop: "0.25rem" }}>
            {APP_TAGLINE}
          </p>
        </div>

        {error && (
          <div style={{
            padding: "0.75rem",
            backgroundColor: "var(--priority-critical-bg)",
            border: "1px solid var(--priority-critical-border)",
            borderRadius: "6px",
            color: "var(--priority-critical-text)",
            fontSize: "0.8125rem",
            display: "flex",
            alignItems: "center",
            gap: "0.5rem",
            marginBottom: "1rem"
          }}>
            <AlertCircle size={16} />
            <span>{error}</span>
          </div>
        )}

        <form onSubmit={handleSubmit}>
          <div style={{ marginBottom: "1rem" }}>
            <label style={{ display: "block", fontSize: "0.8125rem", fontWeight: 600, color: "var(--text-main)", marginBottom: "0.375rem" }}>
              Merchant Email / Account
            </label>
            <input
              type="text"
              className="input"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="merchant@example.com"
              required
            />
          </div>

          <div style={{ marginBottom: "1.25rem" }}>
            <label style={{ display: "block", fontSize: "0.8125rem", fontWeight: 600, color: "var(--text-main)", marginBottom: "0.375rem" }}>
              Password
            </label>
            <input
              type="password"
              className="input"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••••••"
              required
            />
          </div>

          <button
            type="submit"
            className="btn-primary"
            style={{ width: "100%", display: "flex", alignItems: "center", justifyContent: "center", gap: "0.5rem" }}
            disabled={loading}
          >
            {loading ? <span className="spinner" /> : <LogIn size={16} />}
            <span>Sign In to Recovery Command</span>
          </button>
        </form>

        <div style={{
          marginTop: "1.5rem",
          paddingTop: "1rem",
          borderTop: "1px solid var(--border-color)",
          textAlign: "center",
          fontSize: "0.75rem",
          color: "var(--text-muted)"
        }}>
          <span>Authenticate with merchant account configured in backend environment</span>
        </div>
      </div>
    </div>
  )
}

