import * as React from 'react'

import { Button } from './button'

type IconButtonProps = React.ComponentProps<typeof Button> & { 'aria-label': string }

export function IconButton({ size = 'icon', type = 'button', ...props }: IconButtonProps) {
  return <Button size={size} type={type} {...props} />
}
