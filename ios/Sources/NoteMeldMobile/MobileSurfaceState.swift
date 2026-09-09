import Foundation

/// Shared page contract for the iOS host. Agent execution stays in the SDK/runtime.
public enum MobileScreen: String { case home, session, settings, memory, fontSize = "font-size", storage }
public enum AgentLocation: String, Hashable { case local = "本地工作", cloud = "云端工作", remote = "远程电脑" }
public enum ConnectionState: Hashable { case ready, offline, syncing, error }
public struct StorageItem: Identifiable, Equatable { public let id: String; public let title: String; public let detail: String; public var sizeMB: Double }
public struct MobileTask: Identifiable, Equatable, Codable { public let id: String; public let title: String; public let status: String }
public struct MobileMessage: Identifiable, Equatable { public let id = UUID(); public let role: String; public let content: String }
public struct RemoteDeviceDescriptor: Identifiable, Equatable { public let id: String; public let displayName: String; public let platform: String; public let online: Bool; public let publicKey: Data; public let lanEndpoints: [String] }

public struct MobileSurfaceState: Equatable {
    public var screen: MobileScreen = .home
    public var drawerOpen = false
    public var sheet: String?
    public var sending = false
    public var permissionGranted = false
    public var location: AgentLocation = .local
    public var connection: ConnectionState = .ready
    public var selectedModel = "Auto"
    public var theme = "system"
    public var language = "跟随系统"
    public var fontSize = 16
    public var followSystemFont = false
    public var notificationsEnabled = true
    public var memoryDraft = ""
    public var memories: [String] = []
    public var tasks: [MobileTask] = []
    public var activeTaskID: String?
    public var activeTaskTitle: String?
    public var messages: [MobileMessage] = []
    public var inputText = ""
    public var cloudURL = "http://127.0.0.1:8583"
    public var cloudUsername = ""
    public var cloudPassword = ""
    public var cloudStatus = "未连接"
    public var remoteDevices: [RemoteDeviceDescriptor] = []
    public var selectedRemoteDeviceID: String?
    public var storage: [StorageItem] = []
    public init() {}

    public static func load() -> MobileSurfaceState {
        var state = MobileSurfaceState()
        let defaults = UserDefaults.standard
        state.selectedModel = defaults.string(forKey: "notemeld.mobile.model") ?? "Auto"
        state.theme = defaults.string(forKey: "notemeld.mobile.theme") ?? "system"
        state.language = defaults.string(forKey: "notemeld.mobile.language") ?? "跟随系统"
        state.fontSize = defaults.object(forKey: "notemeld.mobile.fontSize") as? Int ?? 16
        state.followSystemFont = defaults.bool(forKey: "notemeld.mobile.followSystemFont")
        state.notificationsEnabled = defaults.object(forKey: "notemeld.mobile.notifications") as? Bool ?? true
        state.cloudURL = defaults.string(forKey: "notemeld.mobile.cloudURL") ?? "http://127.0.0.1:8583"
        state.cloudUsername = defaults.string(forKey: "notemeld.mobile.cloudUsername") ?? ""
        state.memories = defaults.stringArray(forKey: "notemeld.mobile.memories") ?? []
        if let data = defaults.data(forKey: "notemeld.mobile.tasks"), let tasks = try? JSONDecoder().decode([MobileTask].self, from: data) { state.tasks = tasks }
        state.storage = storageItems()
        return state
    }

    public func persist() {
        let defaults = UserDefaults.standard
        defaults.set(selectedModel, forKey: "notemeld.mobile.model")
        defaults.set(theme, forKey: "notemeld.mobile.theme")
        defaults.set(language, forKey: "notemeld.mobile.language")
        defaults.set(fontSize, forKey: "notemeld.mobile.fontSize")
        defaults.set(followSystemFont, forKey: "notemeld.mobile.followSystemFont")
        defaults.set(notificationsEnabled, forKey: "notemeld.mobile.notifications")
        defaults.set(cloudURL, forKey: "notemeld.mobile.cloudURL")
        defaults.set(cloudUsername, forKey: "notemeld.mobile.cloudUsername")
        defaults.set(memories, forKey: "notemeld.mobile.memories")
        if let data = try? JSONEncoder().encode(tasks) { defaults.set(data, forKey: "notemeld.mobile.tasks") }
    }

    public static func clearStorage(_ id: String?) {
        for (key, directory) in storageDirectories() where id == nil || id == key {
            try? FileManager.default.removeItem(at: directory)
            try? FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        }
    }

    public static func cloudAttachmentDirectory() -> URL {
        let directory = storageDirectories()["cloud"]!.appendingPathComponent("attachments", isDirectory: true)
        try? FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        return directory
    }

    public static func storageItems() -> [StorageItem] {
        let directories = storageDirectories()
        return [
            StorageItem(id: "cache", title: "缓存", detail: "接口、预览与附件缓存", sizeMB: sizeMB(directories["cache"]!)),
            StorageItem(id: "cloud", title: "云端对话数据", detail: "本机保存的云端事件与缓存", sizeMB: sizeMB(directories["cloud"]!)),
            StorageItem(id: "local", title: "本机对话数据", detail: "仅保存在本机的会话记录", sizeMB: sizeMB(directories["local"]!)),
            StorageItem(id: "artifacts", title: "下载的产物文件", detail: "沙箱下载的预览与产物", sizeMB: sizeMB(directories["artifacts"]!)),
        ]
    }

    private static func storageDirectories() -> [String: URL] {
        let fileManager = FileManager.default
        let base = fileManager.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("NoteMeld", isDirectory: true)
        let cache = fileManager.urls(for: .cachesDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("NoteMeld", isDirectory: true)
        let directories = [
            "cache": cache,
            "cloud": base.appendingPathComponent("cloud-cache", isDirectory: true),
            "local": base.appendingPathComponent("local", isDirectory: true),
            "artifacts": base.appendingPathComponent("artifacts", isDirectory: true),
        ]
        for directory in directories.values { try? fileManager.createDirectory(at: directory, withIntermediateDirectories: true) }
        return directories
    }

    private static func sizeMB(_ directory: URL) -> Double {
        let fileManager = FileManager.default
        guard let enumerator = fileManager.enumerator(at: directory, includingPropertiesForKeys: [.fileSizeKey], options: [.skipsHiddenFiles]) else { return 0 }
        let bytes = enumerator.compactMap { item -> Int64? in
            guard let url = item as? URL, let values = try? url.resourceValues(forKeys: [.isRegularFileKey, .fileSizeKey]), values.isRegularFile == true else { return nil }
            return Int64(values.fileSize ?? 0)
        }.reduce(0, +)
        return Double(bytes) / (1024 * 1024)
    }
}

public enum MobileSurfaceAction { case navigate(MobileScreen), toggleDrawer, openSheet(String), closeOverlay, setSending(Bool), setPermission(Bool), setLocation(AgentLocation), setConnection(ConnectionState), selectModel(String), setTheme(String), setLanguage(String), setFontSize(Int), setFollowSystemFont(Bool), setNotifications(Bool), setMemoryDraft(String), setTasks([MobileTask]), openTask(String?, String), setMemories([String]), setInputText(String), addMessage(MobileMessage), setCloudURL(String), setCloudUsername(String), setCloudPassword(String), setCloudStatus(String), setRemoteDevices([RemoteDeviceDescriptor]), selectRemoteDevice(String), addMemory, clearStorage(String?) }

public func reduceMobileSurface(_ state: MobileSurfaceState, _ action: MobileSurfaceAction) -> MobileSurfaceState {
    var next = state
    switch action {
    case let .navigate(screen): next.screen = screen; next.drawerOpen = false; next.sheet = nil
    case .toggleDrawer: next.drawerOpen.toggle(); next.sheet = nil
    case let .openSheet(name): next.sheet = name; next.drawerOpen = false
    case .closeOverlay: next.drawerOpen = false; next.sheet = nil
    case let .setSending(value): next.sending = value
    case let .setPermission(value): next.permissionGranted = value
    case let .setLocation(value): next.location = value
    case let .setConnection(value): next.connection = value
    case let .selectModel(value): next.selectedModel = value; next.sheet = nil
    case let .setTheme(value): next.theme = value; next.sheet = nil
    case let .setLanguage(value): next.language = value; next.sheet = nil
    case let .setFontSize(value): next.fontSize = value
    case let .setFollowSystemFont(value): next.followSystemFont = value
    case let .setNotifications(value): next.notificationsEnabled = value
    case let .setMemoryDraft(value): next.memoryDraft = value
    case let .setTasks(value): next.tasks = value
    case let .openTask(id, title): next.activeTaskID = id; next.activeTaskTitle = title; next.screen = .session; next.drawerOpen = false
    case let .setMemories(value): next.memories = value
    case let .setInputText(value): next.inputText = value
    case let .addMessage(value): next.messages.append(value)
    case let .setCloudURL(value): next.cloudURL = value
    case let .setCloudUsername(value): next.cloudUsername = value
    case let .setCloudPassword(value): next.cloudPassword = value
    case let .setCloudStatus(value): next.cloudStatus = value
    case let .setRemoteDevices(value): next.remoteDevices = value; next.selectedRemoteDeviceID = value.first(where: { $0.online })?.id ?? value.first?.id
    case let .selectRemoteDevice(value): next.selectedRemoteDeviceID = value
    case .addMemory: if !next.memoryDraft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty { next.memories.append(next.memoryDraft.trimmingCharacters(in: .whitespacesAndNewlines)); next.memoryDraft = "" }
    case let .clearStorage(id): if let id { next.storage.removeAll { $0.id == id } } else { next.storage.removeAll() }
    }
    return next
}
