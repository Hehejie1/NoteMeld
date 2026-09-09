import SwiftUI
import UIKit
import Security
import UniformTypeIdentifiers

/// Native M01–M06 surface. Agent execution and persistence are supplied by the host/runtime.
public struct MobileSurface: View {
    @State private var state = MobileSurfaceState.load()
    @State private var remoteTransport: RemoteRelayTransport?
    @State private var showingFileImporter = false
    @State private var attachmentNames: [String] = []
    @State private var logURL: URL?
    @State private var savingMemory = false
    public init() {}

    public var body: some View {
        NavigationStack {
            Group {
                switch state.screen {
                case .home: home
                case .session: session
                case .settings: settings
                case .memory: memory
                case .fontSize: font
                case .storage: storage
                }
            }
            .navigationTitle(title)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) { Button("☰") { dispatch(.toggleDrawer) } }
                ToolbarItem(placement: .topBarTrailing) { Button("设置") { dispatch(.navigate(.settings)) } }
            }
            .sheet(isPresented: Binding(get: { state.sheet != nil }, set: { if !$0 { dispatch(.closeOverlay) } })) { sheet }
        .sheet(isPresented: Binding(get: { state.drawerOpen }, set: { if !$0 { dispatch(.closeOverlay) } })) { drawer }
        .fileImporter(isPresented: $showingFileImporter, allowedContentTypes: [.item], allowsMultipleSelection: true) { result in
            if case let .success(urls) = result {
                let root = MobileSurfaceState.cloudAttachmentDirectory()
                try? FileManager.default.removeItem(at: root)
                try? FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
                for url in urls {
                    let accessed = url.startAccessingSecurityScopedResource()
                    defer { if accessed { url.stopAccessingSecurityScopedResource() } }
                    if let data = try? Data(contentsOf: url) {
                        try? data.write(to: root.appendingPathComponent(url.lastPathComponent, isDirectory: false), options: .atomic)
                    }
                }
                attachmentNames = urls.map(\.lastPathComponent)
            }
        }
        }
        .font(.system(size: CGFloat(state.fontSize)))
        .preferredColorScheme(state.theme == "dark" ? .dark : state.theme == "light" ? .light : nil)
        .task {
            while !Task.isCancelled {
                await loadTasks()
                try? await Task.sleep(nanoseconds: 5_000_000_000)
            }
        }
    }

    private var title: String {
        switch state.screen { case .home: "NoteMeld"; case .session: state.activeTaskTitle ?? "新建会话"; case .settings: "设置"; case .memory: "记忆库"; case .fontSize: "字体大小"; case .storage: "存储空间" }
    }
    private func dispatch(_ action: MobileSurfaceAction) {
        state = reduceMobileSurface(state, action)
        if case let .clearStorage(id) = action {
            MobileSurfaceState.clearStorage(id)
            state.storage = MobileSurfaceState.storageItems()
        }
        state.persist()
    }

    private func loadTasks() async {
        guard let url = URL(string: "http://127.0.0.1:8483/api/conversations?limit=20") else { return }
        do {
            let (data, response) = try await URLSession.shared.data(from: url)
            guard (response as? HTTPURLResponse)?.statusCode == 200 else { return }
            let envelope = try JSONDecoder().decode(ConversationEnvelope.self, from: data)
            dispatch(.setTasks(envelope.data))
            dispatch(.setConnection(.ready))
            await loadProjection()
        } catch {
            dispatch(.setConnection(.offline))
        }
    }

    private func loadProjection() async {
        guard let url = URL(string: "http://127.0.0.1:8483/api/mobile/projection?workspace_id=default") else { return }
        guard let (data, response) = try? await URLSession.shared.data(from: url),
              (response as? HTTPURLResponse)?.statusCode == 200,
              let envelope = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let payload = envelope["data"] as? [String: Any],
              let rows = payload["memories"] as? [[String: Any]] else { return }
        dispatch(.setMemories(rows.compactMap { $0["content"] as? String }))
        if let revision = payload["workspace"] as? [String: Any], let value = revision["revision"] as? Int {
            await saveProjectionCursor(revision: value)
        }
    }

    private func saveProjectionCursor(revision: Int) async {
        let installID = UserDefaults.standard.string(forKey: "notemeld-install-id") ?? UUID().uuidString.lowercased()
        UserDefaults.standard.set(installID, forKey: "notemeld-install-id")
        guard let url = URL(string: "http://127.0.0.1:8483/api/mobile/sync-cursor") else { return }
        var request = URLRequest(url: url); request.httpMethod = "PUT"; request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try? JSONSerialization.data(withJSONObject: ["device_id": "ios-\(installID)", "workspace_id": "default", "session_id": "", "snapshot_revision": revision, "event_sequence": 0])
        _ = try? await URLSession.shared.data(for: request)
    }

    private func sendAgent(_ input: String) async {
        do {
            let session = try await postJSON(path: "/api/agent/v1/sessions", body: ["title": "NoteMeld Mobile"])
            guard let sessionId = (session["data"] as? [String: Any])?["id"] as? String else { throw URLError(.badServerResponse) }
            let turn = try await postJSON(path: "/api/agent/v1/sessions/\(sessionId)/turns", body: ["input": input])
            guard let turnId = (turn["data"] as? [String: Any])?["turn_id"] as? String else { throw URLError(.badServerResponse) }
            let (data, response) = try await URLSession.shared.data(from: URL(string: "http://127.0.0.1:8483/api/agent/v1/turns/\(turnId)/events?after_sequence=-1")!)
            guard (response as? HTTPURLResponse)?.statusCode == 200 else { throw URLError(.badServerResponse) }
            for frame in String(decoding: data, as: UTF8.self).components(separatedBy: "\n\n") {
                guard let line = frame.split(separator: "\n").first(where: { $0.hasPrefix("data:") }) else { continue }
                let raw = line.dropFirst(5).trimmingCharacters(in: .whitespaces)
                guard let eventData = raw.data(using: .utf8), let event = try? JSONSerialization.jsonObject(with: eventData) as? [String: Any] else { continue }
                if let payload = event["payload"] as? [String: Any], let content = payload["content"] as? String, !content.isEmpty { dispatch(.addMessage(MobileMessage(role: "assistant", content: content))) }
            }
            dispatch(.setSending(false))
        } catch {
            dispatch(.addMessage(MobileMessage(role: "assistant", content: "Agent 请求失败：\(error.localizedDescription)")))
            dispatch(.setConnection(.offline)); dispatch(.setSending(false))
        }
    }

    private func sendCloudAgent(_ input: String) async {
        do {
            let base = state.cloudURL.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
            guard let token = KeychainToken.load() else { throw URLError(.userAuthenticationRequired) }
            let defaults = UserDefaults.standard
            let sessionID: String
            if let stored = defaults.string(forKey: "notemeld.cloud.sessionID") {
                sessionID = stored
            } else {
                let session = try await cloudRequest(base: base, path: "/v1/sessions", method: "POST", token: token, body: ["kind": "cloud_native", "title": "NoteMeld iOS"])
                guard let created = (session["data"] as? [String: Any])?["id"] as? String else { throw URLError(.badServerResponse) }
                sessionID = created
                defaults.set(created, forKey: "notemeld.cloud.sessionID")
                defaults.set(0, forKey: "notemeld.cloud.eventSequence")
            }
            _ = try await cloudRequest(base: base, path: "/v1/sessions/\(sessionID)/commands", method: "POST", token: token, body: ["request_id": UUID().uuidString, "input": input, "attachments": stagedCloudAttachments()])
            var after = defaults.integer(forKey: "notemeld.cloud.eventSequence")
            for _ in 0..<60 {
                try await Task.sleep(nanoseconds: 500_000_000)
                let events = try await cloudRequest(base: base, path: "/v1/sessions/\(sessionID)/events?after=\(after)", method: "GET", token: token, body: [:])
                guard let rows = events["data"] as? [[String: Any]] else { continue }
                var terminal = false
                for row in rows {
                    after = max(after, row["sequence"] as? Int ?? after)
                    defaults.set(after, forKey: "notemeld.cloud.eventSequence")
                    let payload = row["payload"] as? [String: Any]
                    if let output = payload?["output"] as? String, !output.isEmpty { dispatch(.addMessage(MobileMessage(role: "assistant", content: output))) }
                    let eventType = row["event_type"] as? String ?? ""
                    let status = payload?["status"] as? String ?? ""
                    terminal = terminal || (eventType.hasPrefix("command.") && ["completed", "failed", "cancelled"].contains(status))
                }
                if terminal { dispatch(.setSending(false)); return }
            }
            dispatch(.addMessage(MobileMessage(role: "assistant", content: "Cloud Agent 等待超时")))
            dispatch(.setSending(false))
        } catch {
            dispatch(.addMessage(MobileMessage(role: "assistant", content: "Cloud Agent 请求失败：\(error.localizedDescription)")))
            dispatch(.setConnection(.offline)); dispatch(.setSending(false))
        }
    }

    private func sendRemoteAgent(_ input: String) async {
        do {
            guard let selected = state.remoteDevices.first(where: { $0.id == state.selectedRemoteDeviceID }), selected.publicKey.count == 32 else { throw RemoteError.invalidHandshake }
            guard let token = KeychainToken.load(), let cloud = URL(string: state.cloudURL.trimmingCharacters(in: CharacterSet(charactersIn: "/"))) else { throw URLError(.badURL) }
            let installID = UserDefaults.standard.string(forKey: "notemeld-install-id") ?? UUID().uuidString.lowercased()
            UserDefaults.standard.set(installID, forKey: "notemeld-install-id")
            let controllerID = "ios-\(installID)"
            let session = try await cloudRequest(base: cloud.absoluteString, path: "/v1/sessions", method: "POST", token: token, body: ["kind": "device_remote", "title": "NoteMeld iOS Remote"])
            guard let sessionID = (session["data"] as? [String: Any])?["id"] as? String else { throw URLError(.badServerResponse) }
            let identity = try DeviceIdentityStore.loadOrCreate()
            let transport = RemoteRelayTransport(sessionID: sessionID, controllerID: controllerID, host: .init(id: selected.id, publicKey: selected.publicKey), lanEndpoints: selected.lanEndpoints, cloudURL: cloud, token: token, identity: identity) { event in
                if let payload = event["event"] as? [String: Any], let content = payload["payload"] as? [String: Any], let delta = content["delta"] as? String { DispatchQueue.main.async { dispatch(.addMessage(MobileMessage(role: "assistant", content: delta))) } }
            }
            remoteTransport = transport
            try await transport.connect()
            let receipt = try await transport.send(input: input)
            dispatch(.addMessage(MobileMessage(role: "assistant", content: "远程命令已安全送达主机队列（\(receipt["queue_status"] as? String ?? "queued")）。")))
            dispatch(.setSending(false))
        } catch {
            dispatch(.addMessage(MobileMessage(role: "assistant", content: "远程设备请求失败：\(error.localizedDescription)")))
            dispatch(.setConnection(.error)); dispatch(.setSending(false))
        }
    }

    private func postJSON(path: String, body: [String: Any]) async throws -> [String: Any] {
        let url = URL(string: "http://127.0.0.1:8483\(path)")!
        var request = URLRequest(url: url); request.httpMethod = "POST"; request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONSerialization.data(withJSONObject: body)
        let (data, response) = try await URLSession.shared.data(for: request)
        let status = (response as? HTTPURLResponse)?.statusCode ?? 0
        guard status == 200 || status == 202 else { throw URLError(.badServerResponse) }
        return try JSONSerialization.jsonObject(with: data) as! [String: Any]
    }

    private func loginCloud() async {
        do {
            let base = state.cloudURL.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
            let tokenResponse = try await cloudRequest(base: base, path: "/v1/auth/login", method: "POST", token: nil, body: ["username": state.cloudUsername, "password": state.cloudPassword])
            guard let data = tokenResponse["data"] as? [String: Any], let token = data["token"] as? String else { throw URLError(.badServerResponse) }
            KeychainToken.save(token)
            let installID = UserDefaults.standard.string(forKey: "notemeld-install-id") ?? UUID().uuidString.lowercased()
            UserDefaults.standard.set(installID, forKey: "notemeld-install-id")
            let deviceID = "ios-\(installID)"
            let identity = try DeviceIdentityStore.loadOrCreate()
            _ = try await cloudRequest(base: base, path: "/v1/devices/register", method: "POST", token: token, body: ["device_id": deviceID, "platform": "ios", "display_name": "NoteMeld iOS", "public_key": base64url(identity.publicKey.rawRepresentation)])
            _ = try await cloudRequest(base: base, path: "/v1/devices/\(deviceID)/heartbeat", method: "POST", token: token, body: [:])
            let devicesResponse = try await cloudRequest(base: base, path: "/v1/devices", method: "GET", token: token, body: [:])
            let devices = (devicesResponse["data"] as? [[String: Any]] ?? []).compactMap { row -> RemoteDeviceDescriptor? in
                guard let id = row["id"] as? String, id != deviceID, let publicKey = decodeBase64url(row["public_key"] as? String), publicKey.count == 32 else { return nil }
                let connectivity = row["connectivity"] as? [String: Any] ?? [:]
                return RemoteDeviceDescriptor(id: id, displayName: row["display_name"] as? String ?? id, platform: row["platform"] as? String ?? "unknown", online: row["online"] as? Bool ?? false, publicKey: publicKey, lanEndpoints: connectivity["lan_endpoints"] as? [String] ?? [])
            }
            dispatch(.setRemoteDevices(devices))
            dispatch(.setCloudStatus("已连接 Cloud"))
        } catch { dispatch(.setCloudStatus("Cloud 连接失败：\(error.localizedDescription)")) }
    }

    private func base64url(_ data: Data) -> String { data.base64EncodedString().replacingOccurrences(of: "+", with: "-").replacingOccurrences(of: "/", with: "_").replacingOccurrences(of: "=", with: "") }
    private func decodeBase64url(_ value: String?) -> Data? { guard let value else { return nil }; return Data(base64Encoded: value.replacingOccurrences(of: "-", with: "+").replacingOccurrences(of: "_", with: "/") + String(repeating: "=", count: (4 - value.count % 4) % 4)) }

    private func cloudRequest(base: String, path: String, method: String, token: String?, body: [String: Any]) async throws -> [String: Any] {
        var request = URLRequest(url: URL(string: base + path)!)
        request.httpMethod = method; request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        if let token { request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization") }
        if method != "GET" { request.httpBody = try JSONSerialization.data(withJSONObject: body) }
        let (data, response) = try await URLSession.shared.data(for: request)
        let status = (response as? HTTPURLResponse)?.statusCode ?? 0
        guard 200...299 ~= status else { throw URLError(.badServerResponse) }
        return try JSONSerialization.jsonObject(with: data) as! [String: Any]
    }

    private var home: some View {
        List {
            Section {
                Text("让 Agent 把想法变成可交付的成果。").font(.title2)
                Picker("工作位置", selection: Binding(get: { state.location }, set: { dispatch(.setLocation($0)) })) { ForEach([AgentLocation.local, .cloud, .remote], id: \.self) { Text($0.rawValue).tag($0) } }.pickerStyle(.segmented)
            }
            Section("继续工作") { if state.tasks.isEmpty { Text("暂无已同步会话").foregroundStyle(.secondary) } else { ForEach(Array(state.tasks.prefix(6))) { task in Button { dispatch(.openTask(task.id, task.title)) } label: { VStack(alignment: .leading) { Text(task.title); Text(task.status).font(.caption).foregroundStyle(.secondary) } } } } }
            Button("新建任务") { dispatch(.openTask(nil, "新建会话")) }
        }
    }

    private var session: some View {
        VStack(alignment: .leading) {
            if state.connection == .offline { Label("离线模式：仅可查看已同步内容", systemImage: "wifi.slash").foregroundStyle(.red) }
            if !state.permissionGranted { Button("确认本次 Agent 文件与工具权限") { dispatch(.setPermission(true)) } }
            ScrollView { VStack(alignment: .leading, spacing: 12) { Text("\(state.location.rawValue) Agent · \(state.sending ? "运行中" : "待命")").foregroundStyle(.secondary); ForEach(state.messages) { message in Text(message.content).padding().frame(maxWidth: .infinity, alignment: .leading).background(message.role == "user" ? .blue.opacity(0.08) : .gray.opacity(0.1), in: RoundedRectangle(cornerRadius: 12)) } }.frame(maxWidth: .infinity, alignment: .leading) }.frame(maxHeight: .infinity)
            TextField("继续告诉 Agent 你要完成什么…", text: Binding(get: { state.inputText }, set: { dispatch(.setInputText($0)) })).textFieldStyle(.roundedBorder)
            if !attachmentNames.isEmpty { Text("附件：\(attachmentNames.joined(separator: ", "))").font(.caption).foregroundStyle(.secondary) }
            HStack { Button("⋯") { dispatch(.openSheet("actions")) }; Button("添加文件") { showingFileImporter = true }; Button("全部产物") { dispatch(.openSheet("products")) }; Button(state.selectedModel) { dispatch(.openSheet("model")) }; Button(state.sending ? "发送中…" : "发送") { let input = state.inputText.trimmingCharacters(in: .whitespacesAndNewlines); guard !input.isEmpty else { return }; dispatch(.addMessage(MobileMessage(role: "user", content: input))); dispatch(.setInputText("")); dispatch(.setSending(true)); Task { if state.location == .local { await sendAgent(input) } else if state.location == .cloud { await sendCloudAgent(input) } else { await sendRemoteAgent(input) } } }.buttonStyle(.borderedProminent).disabled(state.connection == .offline || state.sending) }
        }.padding()
    }

    private var settings: some View {
        List {
            Button("记忆库 · \(state.memories.count) 个条目") { dispatch(.navigate(.memory)) }
            Section {
                Button("主题 · \(state.theme == "dark" ? "深色" : state.theme == "light" ? "浅色" : "跟随系统")") { dispatch(.openSheet("theme")) }
                Button("语言 · \(state.language)") { dispatch(.openSheet("language")) }
                Button("字体大小 · \(state.fontSize)px") { dispatch(.navigate(.fontSize)) }
                Toggle("消息通知设置", isOn: Binding(get: { state.notificationsEnabled }, set: { dispatch(.setNotifications($0)) }))
            }
            Section("Cloud 连接") {
                TextField("Cloud 地址", text: Binding(get: { state.cloudURL }, set: { dispatch(.setCloudURL($0)) }))
                TextField("用户名", text: Binding(get: { state.cloudUsername }, set: { dispatch(.setCloudUsername($0)) }))
                SecureField("密码", text: Binding(get: { state.cloudPassword }, set: { dispatch(.setCloudPassword($0)) }))
                HStack { Text(state.cloudStatus).font(.caption); Spacer(); Button("登录并同步") { Task { await loginCloud() } } }
            }
            Section("远程设备") {
                if state.remoteDevices.isEmpty { Text("登录后显示已授权设备").foregroundStyle(.secondary) }
                ForEach(state.remoteDevices) { device in
                    Button { dispatch(.selectRemoteDevice(device.id)); dispatch(.setLocation(.remote)) } label: { HStack { Text(device.displayName); Spacer(); Text(device.online ? "在线" : "离线").font(.caption).foregroundStyle(device.online ? .green : .secondary) } }
                }
            }
            Section {
                if let logURL { ShareLink(item: logURL) { Label("分享日志 · 已生成", systemImage: "square.and.arrow.up") } } else { Button("分享日志 · 生成") { prepareLogFile() } }
                Button("存储空间 · \(String(format: "%.2f MB", totalStorage))") { dispatch(.navigate(.storage)) }
            }
        }
    }

    private var memory: some View {
        List { Section("我的记忆") { ForEach(state.memories, id: \.self) { Text($0) } }; Section { TextField("告诉 NoteMeld 要记住或忘记什么…", text: Binding(get: { state.memoryDraft }, set: { dispatch(.setMemoryDraft($0)) })); Button(savingMemory ? "保存中…" : "添加我的记忆") { Task { await saveMemory() } }.disabled(savingMemory || state.memoryDraft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty) }; Button("复制记忆") { UIPasteboard.general.string = state.memories.joined(separator: "\n") } }
    }

    private func saveMemory() async {
        let content = state.memoryDraft.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !content.isEmpty else { return }
        savingMemory = true
        defer { savingMemory = false }
        do {
            _ = try await postJSON(path: "/api/mobile/memories", body: ["workspace_id": "default", "content": content, "source": "ios"])
            dispatch(.setMemoryDraft(""))
            await loadProjection()
        } catch {
            dispatch(.setConnection(.error))
        }
    }
    private var font: some View { List { Text("NoteMeld Agent\n字号预览：\(state.fontSize)px").font(.system(size: CGFloat(state.fontSize))); Toggle("跟随系统", isOn: Binding(get: { state.followSystemFont }, set: { dispatch(.setFollowSystemFont($0)) })); Slider(value: Binding(get: { Double(state.fontSize) }, set: { dispatch(.setFontSize(Int($0))) }), in: 13...19, step: 1); Button("确认保存") { state.persist() } } }
    private var totalStorage: Double { state.storage.reduce(0) { $0 + $1.sizeMB } }
    private var storage: some View { List { Text("NoteMeld 占用空间：\(String(format: "%.2f MB", totalStorage))"); Button("全部清除", role: .destructive) { dispatch(.clearStorage(nil)) }; ForEach(state.storage) { item in HStack { VStack(alignment: .leading) { Text(item.title); Text(item.detail).font(.caption).foregroundStyle(.secondary) }; Spacer(); Text(String(format: "%.2f MB", item.sizeMB)); Button("清除") { dispatch(.clearStorage(item.id)) } } } } }
    private var drawer: some View { NavigationStack { List { Section("工作位置") { ForEach([AgentLocation.local, .cloud, .remote], id: \.self) { location in Button(location.rawValue) { dispatch(.setLocation(location)) } } }; Section("任务") { if state.tasks.isEmpty { Text("暂无已同步会话").foregroundStyle(.secondary) } else { ForEach(state.tasks) { task in Button("\(task.title) · \(task.status)") { dispatch(.openTask(task.id, task.title)) } } } } }.navigationTitle("NoteMeld") } }
    @ViewBuilder private var sheet: some View { if state.sheet == "model" { List { ForEach(["Auto", "Hy4 preview", "Hy3", "GLM-5.3", "Kimi-K3"], id: \.self) { model in Button(model) { dispatch(.selectModel(model)) } } }.presentationDetents([.medium]) } else if state.sheet == "theme" { List { ForEach([("system", "跟随系统"), ("light", "浅色"), ("dark", "深色")], id: \.0) { value, label in Button(label) { dispatch(.setTheme(value)) } } }.presentationDetents([.medium]) } else if state.sheet == "products" { List { Text("当前会话暂无可下载产物").foregroundStyle(.secondary) } } else if state.sheet == "actions" { List { Button("全部产物") { dispatch(.openSheet("products")) }; Button("删除对话", role: .destructive) { Task { await deleteConversation() } }.disabled(state.activeTaskID == nil) }.presentationDetents([.medium]) } else { List { ForEach(["跟随系统", "简体中文", "繁體中文", "English"], id: \.self) { language in Button(language) { dispatch(.setLanguage(language)) } } }.presentationDetents([.medium]) } }

    private func deleteConversation() async {
        guard let id = state.activeTaskID, let url = URL(string: "http://127.0.0.1:8483/api/conversations/\(id)") else { return }
        var request = URLRequest(url: url); request.httpMethod = "DELETE"
        do {
            let (_, response) = try await URLSession.shared.data(for: request)
            guard (response as? HTTPURLResponse).map({ 200...299 ~= $0.statusCode }) == true else { throw URLError(.badServerResponse) }
            dispatch(.setTasks(state.tasks.filter { $0.id != id })); dispatch(.navigate(.home))
        } catch { dispatch(.setConnection(.error)) }
    }

    private func prepareLogFile() {
        let body = "NoteMeld mobile diagnostics\nplatform=iOS\nconnection=\(state.connection)\ncloud=\(state.cloudStatus)\nattachments=\(attachmentNames.count)\n"
        let url = FileManager.default.temporaryDirectory.appendingPathComponent("notemeld-mobile-diagnostics.txt")
        try? body.data(using: .utf8)?.write(to: url)
        logURL = url
    }

    private func stagedCloudAttachments() -> [[String: Any]] {
        let root = MobileSurfaceState.cloudAttachmentDirectory()
        guard let files = try? FileManager.default.contentsOfDirectory(at: root, includingPropertiesForKeys: [.fileSizeKey], options: [.skipsHiddenFiles]) else { return [] }
        return files.compactMap { url in
            guard let data = try? Data(contentsOf: url), data.count <= 10 * 1024 * 1024 else { return nil }
            let type = UTType(filenameExtension: url.pathExtension)?.preferredMIMEType ?? "application/octet-stream"
            return ["name": url.lastPathComponent, "size": data.count, "type": type, "content_base64": data.base64EncodedString()]
        }
    }
}

private struct ConversationEnvelope: Decodable { let data: [MobileTask] }

private enum KeychainToken {
    static let service = "com.notemeld.mobile.cloud"
    static func save(_ token: String) {
        let data = Data(token.utf8)
        SecItemDelete([kSecClass: kSecClassGenericPassword, kSecAttrService: service] as CFDictionary)
        SecItemAdd([kSecClass: kSecClassGenericPassword, kSecAttrService: service, kSecAttrAccessible: kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly, kSecValueData: data] as CFDictionary, nil)
    }
    static func load() -> String? {
        let query: [String: Any] = [kSecClass as String: kSecClassGenericPassword, kSecAttrService as String: service, kSecReturnData as String: true, kSecMatchLimit as String: kSecMatchLimitOne]
        var result: CFTypeRef?
        guard SecItemCopyMatching(query as CFDictionary, &result) == errSecSuccess, let data = result as? Data else { return nil }
        return String(data: data, encoding: .utf8)
    }
}
