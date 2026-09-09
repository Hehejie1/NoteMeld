export enum MobileScreen { Home, Session, Settings, Memory, FontSize, Storage }
export enum AgentLocation { Local = '本地工作', Cloud = '云端工作', Remote = '远程电脑' }
export enum ConnectionState { Ready, Offline, Syncing, Error }

export class StorageItem {
  id: string = ''
  title: string = ''
  detail: string = ''
  sizeMb: number = 0
  constructor(id: string, title: string, detail: string, sizeMb: number) {
    this.id = id
    this.title = title
    this.detail = detail
    this.sizeMb = sizeMb
  }
}

export class MobileTask {
  id: string = ''
  title: string = ''
  status: string = ''
  constructor(id: string, title: string, status: string) {
    this.id = id
    this.title = title
    this.status = status
  }
}

export class RemoteDevice {
  id: string = ''
  displayName: string = ''
  publicKey: string = ''
  online: boolean = false
  lanEndpoints: string[] = []
  constructor(id: string, displayName: string, publicKey: string, online: boolean, lanEndpoints: string[] = []) { this.id = id; this.displayName = displayName; this.publicKey = publicKey; this.online = online; this.lanEndpoints = lanEndpoints }
}

export class MobileMessage {
  role: string = ''
  content: string = ''
  constructor(role: string, content: string) { this.role = role; this.content = content }
}

export class MobileSurfaceState {
  screen: MobileScreen = MobileScreen.Home
  drawerOpen: boolean = false
  sheet: string = ''
  sending: boolean = false
  permissionGranted: boolean = false
  location: AgentLocation = AgentLocation.Local
  connection: ConnectionState = ConnectionState.Ready
  selectedModel: string = 'Auto'
  language: string = '跟随系统'
  fontSize: number = 16
  followSystemFont: boolean = false
  notificationsEnabled: boolean = true
  memoryDraft: string = ''
  memories: string[] = []
  tasks: MobileTask[] = []
  activeTaskTitle: string = ''
  activeTaskId: string = ''
  remoteDevices: RemoteDevice[] = []
  messages: MobileMessage[] = []
  attachments: string[] = []
  inputText: string = ''
  cloudURL: string = 'http://127.0.0.1:8583'
  cloudUsername: string = ''
  cloudPassword: string = ''
  cloudStatus: string = '未连接 Cloud'
  storage: StorageItem[] = []
}

export interface MobileSurfaceAction {
  kind: string
  screen?: MobileScreen
  name?: string
  value?: string | number | boolean | string[] | MobileMessage
  devices?: RemoteDevice[]
  id?: string | null
}

export function reduceMobileSurface(state: MobileSurfaceState, action: MobileSurfaceAction): MobileSurfaceState {
  switch (action.kind) {
    case 'navigate': state.screen = action.screen as MobileScreen; state.drawerOpen = false; state.sheet = ''; break
    case 'openTask': state.activeTaskId = action.id ?? ''; state.activeTaskTitle = action.value as string; state.screen = MobileScreen.Session; state.drawerOpen = false; break
    case 'toggleDrawer': state.drawerOpen = !state.drawerOpen; state.sheet = ''; break
    case 'openSheet': state.sheet = action.name as string; state.drawerOpen = false; break
    case 'closeOverlay': state.drawerOpen = false; state.sheet = ''; break
    case 'setSending': state.sending = action.value as boolean; break
    case 'setPermission': state.permissionGranted = action.value as boolean; break
    case 'setLocation': state.location = action.value as AgentLocation; break
    case 'setFontSize': state.fontSize = action.value as number; break
    case 'setFollowSystemFont': state.followSystemFont = action.value as boolean; break
    case 'setNotifications': state.notificationsEnabled = action.value as boolean; break
    case 'setMemoryDraft': state.memoryDraft = action.value as string; break
    case 'setInputText': state.inputText = action.value as string; break
    case 'addMessage': state.messages.push(action.value as MobileMessage); break
    case 'addAttachment': state.attachments.push(action.value as string); break
    case 'setCloudURL': state.cloudURL = action.value as string; break
    case 'setCloudUsername': state.cloudUsername = action.value as string; break
    case 'setCloudPassword': state.cloudPassword = action.value as string; break
    case 'setCloudStatus': state.cloudStatus = action.value as string; break
    case 'setRemoteDevices': state.remoteDevices = action.devices ?? []; break
    case 'selectModel': state.selectedModel = action.value as string; state.sheet = ''; break
    case 'setLanguage': state.language = action.value as string; state.sheet = ''; break
    case 'addMemory': if (state.memoryDraft.trim().length > 0) { state.memories.push(state.memoryDraft.trim()); state.memoryDraft = '' } break
    case 'setMemories': state.memories = action.value as string[]; break
    case 'clearStorage': if (action.id === null) state.storage = []; else state.storage = state.storage.filter((item: StorageItem) => item.id !== action.id); break
  }
  return state
}
