import React, { createContext, useContext, useState } from "react"
import { setAuthToken } from "../api/client"
import type { User } from "../api/types"

interface AuthContextType {
  user: User | null
  token: string | null
  login: (token: string, user: User) => void
  logout: () => void
  isAuthenticated: boolean
}

const AuthContext = createContext<AuthContextType | undefined>(undefined)

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  // Stored strictly in React state / memory, NOT in localStorage
  const [user, setUser] = useState<User | null>(null)
  const [token, setToken] = useState<string | null>(null)

  const login = (newToken: string, newUser: User) => {
    setToken(newToken)
    setUser(newUser)
    setAuthToken(newToken)
  }

  const logout = () => {
    setToken(null)
    setUser(null)
    setAuthToken(null)
  }

  return (
    <AuthContext.Provider
      value={{
        user,
        token,
        login,
        logout,
        isAuthenticated: !!token,
      }}
    >
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth(): AuthContextType {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider")
  }
  return context
}

