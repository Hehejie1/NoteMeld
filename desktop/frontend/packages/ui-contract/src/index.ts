/** Stable vocabulary shared by UI packages and product surfaces. */
export const uiContractVersion = '0.1.0' as const

export const uiStates = ['idle', 'loading', 'empty', 'error', 'offline', 'success'] as const
export type UiState = (typeof uiStates)[number]

export const uiThemes = ['light', 'dark', 'system'] as const
export type UiTheme = (typeof uiThemes)[number]

export interface UiStatus<T = unknown> {
  state: UiState
  data?: T
  message?: string
  retryable?: boolean
}

export interface UiActionResult {
  ok: boolean
  message?: string
}

export const uiContract = {
  version: uiContractVersion,
  states: uiStates,
  themes: uiThemes,
} as const
