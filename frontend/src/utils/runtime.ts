export interface NoteMeldRuntimeConfig {
  apiBaseUrl?: string;
  screenshotBaseUrl?: string;
  mode?: string;
  desktopEmbedded?: boolean;
  sessionToken?: string;
}

declare global {
  interface Window {
    __NOTEMELD_RUNTIME__?: NoteMeldRuntimeConfig;
    __TAURI_INTERNALS__?: unknown;
  }
}

const RUNTIME_REGISTER_MAX_RETRIES = 3;
const RUNTIME_REGISTER_RETRY_DELAY_MS = 1000;
let pageLoadRuntimeRegistrationPromise: Promise<void> | null = null;

function readRuntimeConfig(): NoteMeldRuntimeConfig {
  if (typeof window === 'undefined') {
    return {};
  }

  return window.__NOTEMELD_RUNTIME__ || {};
}

export function shouldUseDesktopRuntime(): boolean {
  if (typeof window === 'undefined') {
    return false;
  }

  if (readRuntimeConfig().desktopEmbedded) {
    return true;
  }

  if (typeof window.__TAURI_INTERNALS__ !== 'undefined') {
    return true;
  }

  return /tauri/i.test(window.navigator?.userAgent || '');
}

async function waitForTauriInvokeReady(timeoutMs = 1500): Promise<boolean> {
  if (typeof window === 'undefined') {
    return false;
  }

  const startedAt = Date.now();
  while (Date.now() - startedAt < timeoutMs) {
    if (typeof window.__TAURI_INTERNALS__ !== 'undefined') {
      return true;
    }
    await new Promise(resolve => setTimeout(resolve, 25));
  }

  return typeof window.__TAURI_INTERNALS__ !== 'undefined';
}

function waitForPageLoad(): Promise<void> {
  if (typeof window === 'undefined' || typeof document === 'undefined') {
    return Promise.resolve();
  }

  if (document.readyState === 'complete') {
    return Promise.resolve();
  }

  return new Promise(resolve => {
    window.addEventListener('load', () => resolve(), { once: true });
  });
}

function delay(ms: number): Promise<void> {
  return new Promise(resolve => setTimeout(resolve, ms));
}

async function bootstrapDesktopRuntime(): Promise<void> {
  if (typeof window === 'undefined' || window.__NOTEMELD_RUNTIME__) {
    return;
  }

  const tauriReady = await waitForTauriInvokeReady();
  if (!tauriReady) {
    throw new Error('tauri invoke bridge is not ready');
  }

  const { invoke } = await import('@tauri-apps/api/core');
  const runtimeBootstrap = await invoke<string>('desktop_runtime_bootstrap');

  if (runtimeBootstrap.trim()) {
    window.eval(runtimeBootstrap);
  }
}

export async function ensureDesktopRuntimeReady(): Promise<void> {
  await bootstrapDesktopRuntime();
}

export async function initializeDesktopRuntime(): Promise<void> {
  try {
    await ensureDesktopRuntimeReady();
  } catch (error) {
    console.warn('failed to initialize desktop runtime before app mount', error);
  }
}

async function registerDesktopRuntimeWithRetry(): Promise<void> {
  let lastError: unknown;

  for (let attempt = 1; attempt <= RUNTIME_REGISTER_MAX_RETRIES; attempt++) {
    try {
      await bootstrapDesktopRuntime();
      return;
    } catch (error) {
      lastError = error;
      console.warn(
        `[NoteMeld] desktop runtime registration failed on attempt ${attempt}/${RUNTIME_REGISTER_MAX_RETRIES}`,
        error,
      );

      if (attempt < RUNTIME_REGISTER_MAX_RETRIES) {
        await delay(RUNTIME_REGISTER_RETRY_DELAY_MS);
      }
    }
  }

  console.warn('failed to initialize desktop runtime after page load retries', lastError);
}

export function registerDesktopRuntimeOnPageLoad(): Promise<void> {
  if (typeof window === 'undefined' || window.__NOTEMELD_RUNTIME__) {
    return Promise.resolve();
  }

  if (!pageLoadRuntimeRegistrationPromise) {
    pageLoadRuntimeRegistrationPromise = (async () => {
      await waitForPageLoad();
      await registerDesktopRuntimeWithRetry();
    })().finally(() => {
      pageLoadRuntimeRegistrationPromise = null;
    });
  }

  return pageLoadRuntimeRegistrationPromise;
}

export function getRuntimeApiBaseUrl(): string | undefined {
  const value = readRuntimeConfig().apiBaseUrl?.trim();
  return value || undefined;
}

export function getRuntimeScreenshotBaseUrl(): string | undefined {
  const value = readRuntimeConfig().screenshotBaseUrl?.trim();
  return value || undefined;
}

export function getRuntimeMode(): string | undefined {
  const value = readRuntimeConfig().mode?.trim();
  return value || undefined;
}

export function getRuntimeSessionToken(): string | undefined {
  const value = readRuntimeConfig().sessionToken?.trim();
  return value || undefined;
}

export function isDesktopEmbedded(): boolean {
  return Boolean(readRuntimeConfig().desktopEmbedded);
}

export async function openExternalUrl(url: string): Promise<void> {
  if (isDesktopEmbedded()) {
    const { invoke } = await import('@tauri-apps/api/core');
    await invoke('open_external_url', { url });
    return;
  }

  if (typeof document !== 'undefined') {
    const link = document.createElement('a');
    link.href = url;
    link.target = '_blank';
    link.rel = 'noopener noreferrer';
    link.style.display = 'none';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    return;
  }

  window.open(url, '_blank');
}
