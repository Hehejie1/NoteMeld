import * as React from 'react'

import { cn } from './cn'

const List = React.forwardRef<HTMLUListElement, React.HTMLAttributes<HTMLUListElement>>(({ className, ...props }, ref) => <ul ref={ref} role="list" className={cn('divide-y divide-border', className)} {...props} />)
List.displayName = 'List'
const ListItem = React.forwardRef<HTMLLIElement, React.LiHTMLAttributes<HTMLLIElement>>(({ className, ...props }, ref) => <li ref={ref} className={cn('flex min-w-0 items-center gap-3 px-3 py-2', className)} {...props} />)
ListItem.displayName = 'ListItem'

export { List, ListItem }
