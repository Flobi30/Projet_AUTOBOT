import React, { createContext, useContext, ReactNode } from 'react'

interface DomainContextType {
  isPublicDomain: boolean
  isPrivateDomain: boolean
  currentDomain: string
}

const DomainContext = createContext<DomainContextType | undefined>(undefined)

export const useDomain = () => {
  const context = useContext(DomainContext)
  if (context === undefined) {
    throw new Error('useDomain must be used within a DomainProvider')
  }
  return context
}

interface DomainProviderProps {
  children: ReactNode
}

export const DomainProvider: React.FC<DomainProviderProps> = ({ children }) => {
  const currentDomain = window.location.hostname
  const isPublicDomain = currentDomain.includes('stripe-autobot.fr')
  const isPrivateDomain = currentDomain.includes('144.76.16.177') || currentDomain === 'localhost'

  const value = {
    isPublicDomain,
    isPrivateDomain,
    currentDomain
  }

  return <DomainContext.Provider value={value}>{children}</DomainContext.Provider>
}
