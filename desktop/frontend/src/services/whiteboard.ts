import request from '@/utils/request'
import type { WhiteboardSelectionContextRef } from './chat'
import type {
  MutateWhiteboardPayload,
  WhiteboardContextPayload,
  WhiteboardMutationResult,
  WhiteboardPublishPayload,
  WhiteboardPublishResult,
  WhiteboardSnapshot,
  WhiteboardSummary,
} from '@/pages/HomePage/whiteboard/types'

const conversationPath = (conversationId: string) =>
  `/conversations/${encodeURIComponent(conversationId)}/whiteboards`

const whiteboardPath = (conversationId: string, whiteboardId: string) =>
  `${conversationPath(conversationId)}/${encodeURIComponent(whiteboardId)}`

export interface RegisterWhiteboardAssetPayload {
  upload_id: string
  file_name: string
  content_type: string
  file_kind: 'markdown' | 'audio' | 'video' | 'document' | 'image'
}

export interface RegisteredWhiteboardAsset extends RegisterWhiteboardAssetPayload {
  asset_id: string
  source_url: string
}

export const listWhiteboards = async (conversationId: string): Promise<WhiteboardSummary[]> =>
  request.get(conversationPath(conversationId)) as unknown as Promise<WhiteboardSummary[]>

export const createWhiteboard = async (
  conversationId: string,
  payload: { title: string; description?: string },
): Promise<WhiteboardSnapshot> =>
  request.post(conversationPath(conversationId), payload) as unknown as Promise<WhiteboardSnapshot>

export const getWhiteboard = async (
  conversationId: string,
  whiteboardId: string,
): Promise<WhiteboardSnapshot> =>
  request.get(whiteboardPath(conversationId, whiteboardId)) as unknown as Promise<WhiteboardSnapshot>

export const deleteWhiteboard = async (
  conversationId: string,
  whiteboardId: string,
): Promise<{ deleted: boolean }> =>
  request.delete(whiteboardPath(conversationId, whiteboardId)) as unknown as Promise<{ deleted: boolean }>

export const mutateWhiteboard = async (
  conversationId: string,
  whiteboardId: string,
  payload: MutateWhiteboardPayload,
): Promise<WhiteboardMutationResult> =>
  request.post(
    `${whiteboardPath(conversationId, whiteboardId)}/mutations`,
    payload,
  ) as unknown as Promise<WhiteboardMutationResult>

export const createWhiteboardContext = async (
  conversationId: string,
  whiteboardId: string,
  payload: WhiteboardContextPayload,
): Promise<WhiteboardSelectionContextRef> =>
  request.post(
    `${whiteboardPath(conversationId, whiteboardId)}/context`,
    payload,
  ) as unknown as Promise<WhiteboardSelectionContextRef>

export const registerWhiteboardAsset = async (
  conversationId: string,
  whiteboardId: string,
  payload: RegisterWhiteboardAssetPayload,
): Promise<RegisteredWhiteboardAsset> =>
  request.post(
    `${whiteboardPath(conversationId, whiteboardId)}/assets`,
    payload,
  ) as unknown as Promise<RegisteredWhiteboardAsset>

export const publishWhiteboard = async (
  conversationId: string,
  whiteboardId: string,
  payload: WhiteboardPublishPayload,
): Promise<WhiteboardPublishResult> =>
  request.post(
    `${whiteboardPath(conversationId, whiteboardId)}/publish-note`,
    payload,
    { timeout: 0 },
  ) as unknown as Promise<WhiteboardPublishResult>

export const seedWhiteboardFromLearningCanvas = async (
  conversationId: string,
  canvasId: string,
): Promise<WhiteboardSnapshot> =>
  request.post(
    `${conversationPath(conversationId)}/from-learning-canvas/${encodeURIComponent(canvasId)}`,
  ) as unknown as Promise<WhiteboardSnapshot>
