import * as React from 'react'

import { cn } from './cn'

const Navigation = React.forwardRef<HTMLElement, React.HTMLAttributes<HTMLElement>>(({ className, ...props }, ref) => <nav ref={ref} className={cn('flex items-center gap-2', className)} {...props} />)
Navigation.displayName = 'Navigation'
const Sidebar = React.forwardRef<HTMLElement, React.HTMLAttributes<HTMLElement>>(({ className, ...props }, ref) => <aside ref={ref} className={cn('flex h-full w-64 flex-col border-r bg-background', className)} {...props} />)
Sidebar.displayName = 'Sidebar'
const AppBar = React.forwardRef<HTMLElement, React.HTMLAttributes<HTMLElement>>(({ className, ...props }, ref) => <header ref={ref} className={cn('flex min-h-12 items-center gap-3 border-b px-4', className)} {...props} />)
AppBar.displayName = 'AppBar'

export { Navigation, Sidebar, AppBar }
