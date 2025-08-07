import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react'
import axios from 'axios'
import jwtDecode from 'jwt-decode'

interface User {
  username: string
  role: string
  exp: number
}

interface AuthContextType {
  user: User | null
  login: (username: string, password: string, licenseKey: string) => Promise<boolean>
  logout: () => void
  isAuthenticated: boolean
  loading: boolean
}

const AuthContext = createContext<AuthContextType | undefined>(undefined)

export const useAuth = () => {
  const context = useContext(AuthContext)
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return context
}

interface AuthProviderProps {
  children: ReactNode
}

export const AuthProvider: React.FC<AuthProviderProps> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const token = localStorage.getItem('access_token')
    if (token) {
      try {
        const decoded = jwtDecode<User>(token)
        if (decoded.exp * 1000 > Date.now()) {
          setUser(decoded)
          axios.defaults.headers.common['Authorization'] = `Bearer ${token}`
        } else {
          localStorage.removeItem('access_token')
        }
      } catch (error) {
        localStorage.removeItem('access_token')
      }
    }
    setLoading(false)
  }, [])

  const login = async (username: string, password: string, licenseKey: string): Promise<boolean> => {
    try {
      const response = await axios.post('/api/login', {
        username,
        password,
        license_key: licenseKey
      })

      const { access_token } = response.data
      localStorage.setItem('access_token', access_token)
      axios.defaults.headers.common['Authorization'] = `Bearer ${access_token}`
      
      const decoded = jwtDecode<User>(access_token)
      setUser(decoded)
      
      return true
    } catch (error) {
      return false
    }
  }

  const logout = () => {
    localStorage.removeItem('access_token')
    delete axios.defaults.headers.common['Authorization']
    setUser(null)
  }

  const value = {
    user,
    login,
    logout,
    isAuthenticated: !!user,
    loading
  }

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
