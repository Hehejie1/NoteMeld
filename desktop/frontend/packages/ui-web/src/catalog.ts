import { uiContractVersion } from '@notemeld/ui-contract'

export const uiWebCatalog = {
  primitives: [
    'Button',
    'IconButton',
    'Input',
    'Textarea',
    'Select',
    'Checkbox',
    'Switch',
    'Tabs',
    'Card',
    'Badge',
    'Alert',
    'Dialog',
    'Tooltip',
    'ScrollArea',
    'Resizable',
    'Toaster',
    'ThemeProvider',
    'IconButton',
    'List',
    'Table',
    'Navigation',
    'Sidebar',
    'AppBar',
    'Popover',
    'Sheet',
    'Drawer',
  ],
  states: ['Empty', 'Error', 'Offline', 'Loading', 'Progress', 'Skeleton'],
  tokens: ['color', 'font', 'space', 'radius', 'control', 'focus', 'motion'],
  contractVersion: uiContractVersion,
} as const

export type UiWebPrimitive = (typeof uiWebCatalog.primitives)[number]
export type UiWebState = (typeof uiWebCatalog.states)[number]
