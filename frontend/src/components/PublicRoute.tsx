import React, { ReactNode } from 'react'
import { useDomain } from '../contexts/DomainContext'

interface PublicRouteProps {
  children: ReactNode
}

const PublicRoute: React.FC<PublicRouteProps> = ({ children }) => {
  const { isPublicDomain } = useDomain()

  if (!isPublicDomain) {
    return <div>Access denied - This page is only available on the public domain</div>
  }

  return <>{children}</>
}

export default PublicRoute
