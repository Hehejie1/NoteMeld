import * as React from 'react'
import * as PopoverPrimitive from '@radix-ui/react-popover'

import { cn } from './cn'

const Popover = PopoverPrimitive.Root
const PopoverTrigger = PopoverPrimitive.Trigger
const PopoverAnchor = PopoverPrimitive.Anchor
const PopoverContent = ({ className, align = 'center', sideOffset = 4, ...props }: React.ComponentProps<typeof PopoverPrimitive.Content>) => <PopoverPrimitive.Portal><PopoverPrimitive.Content align={align} sideOffset={sideOffset} className={cn('z-50 w-72 rounded-md border bg-popover p-4 text-popover-foreground shadow-md outline-none', className)} {...props} /></PopoverPrimitive.Portal>

export { Popover, PopoverTrigger, PopoverAnchor, PopoverContent }
