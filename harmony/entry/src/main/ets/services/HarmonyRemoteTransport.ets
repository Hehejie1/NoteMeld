import webSocket from '@ohos.net.webSocket';
import util from '@ohos.util';
import { HarmonyKeyPair, HarmonyRemoteCrypto } from './HarmonyRemoteCrypto';

export interface HarmonyRemoteDevice {
  id: string;
  publicKey: Uint8Array;
  lanEndpoints: string[];
}

/** Native Harmony transport for the shared LAN/Relay RemoteFrame protocol. */
export class HarmonyRemoteTransport {
  private socket: webSocket.WebSocket | null = null;
  private readonly sessionId: string;
  private readonly controllerId: string;
  private readonly host: HarmonyRemoteDevice;
  private readonly cloudURL: string;
  private readonly token: string;
  private readonly identity: HarmonyKeyPair;
  private readonly pending: Array<(value: string) => void> = [];
  private readonly messages: string[] = [];
  private sessionKey: Uint8Array | null = null;
  private sequence: number = 1;
  private authorityEpoch: number = 1;

  constructor(sessionId: string, controllerId: string, host: HarmonyRemoteDevice, cloudURL: string, token: string, identity: HarmonyKeyPair) {
    this.sessionId = sessionId; this.controllerId = controllerId; this.host = host; this.cloudURL = cloudURL.replace(/\/$/, ''); this.token = token; this.identity = identity;
  }

  async connect(): Promise<void> {
    let lastError: Error | null = null;
    for (let endpoint of this.host.lanEndpoints) {
      try {
        await this.open(`ws://${endpoint}/v1/lan/connect/${HarmonyRemoteTransport.escape(this.sessionId)}`, false);
        await this.lanAuthorization();
        await this.handshake(false);
        return;
      } catch (error) { lastError = new Error(String(error)); await this.closeSocket(); }
    }
    try {
      await this.open(`${HarmonyRemoteTransport.websocketScheme(this.cloudURL)}/v1/relay/connect/${HarmonyRemoteTransport.escape(this.sessionId)}?device_id=${HarmonyRemoteTransport.escape(this.controllerId)}`, true);
      await this.handshake(true);
    } catch (error) { await this.closeSocket(); throw new Error(lastError === null ? String(error) : lastError.message); }
  }

  async send(input: string, requestId: string): Promise<Record<string, Object>> {
    if (this.sessionKey === null || this.socket === null) throw new Error('Harmony remote transport is not connected');
    if (input.trim().length === 0) throw new Error('remote input is empty');
    let frameId = `${Date.now()}-${this.sequence}`;
    let sequence = this.sequence + 1;
    let base: Record<string, Object> = JSON.parse('{}') as Record<string, Object>;
    base['authority_epoch'] = this.authorityEpoch; base['frame_id'] = frameId; base['frame_type'] = 'command'; base['protocol_version'] = 'notemeld.sync.v1'; base['recipient_device_id'] = this.host.id; base['sender_device_id'] = this.controllerId; base['sequence'] = sequence; base['session_id'] = this.sessionId;
    let nonce = await HarmonyRemoteCrypto.random(12);
    let withNonce: Record<string, Object> = HarmonyRemoteTransport.copy(base); withNonce['nonce'] = HarmonyRemoteCrypto.base64(nonce);
    let aad = HarmonyRemoteTransport.canonical(withNonce);
    let encrypted = await HarmonyRemoteCrypto.encrypt(this.sessionKey, HarmonyRemoteTransport.utf8(JSON.stringify({ request_id: requestId, input })), HarmonyRemoteTransport.utf8(aad), nonce);
    let frame: Record<string, Object> = HarmonyRemoteTransport.copy(withNonce); frame['ciphertext'] = HarmonyRemoteCrypto.base64(encrypted.ciphertext);
    await this.socket.send(JSON.stringify(frame));
    this.sequence = sequence;
    while (true) {
      let response = JSON.parse(await this.nextMessage()) as Record<string, Object>;
      if (String(response['type'] ?? '') === 'failed' || String(response['type'] ?? '') === 'rejected') throw new Error(String(response['error'] ?? 'remote transport rejected'));
      if (String(response['frame_type'] ?? '') !== 'receipt' && String(response['frame_type'] ?? '') !== 'event') continue;
      let payload = await this.decryptFrame(response);
      if (String(response['frame_type'] ?? '') === 'event') {
        if (String(payload['request_id'] ?? '') !== requestId) continue;
        let event = payload['event'] as Record<string, Object> | undefined;
        let eventType = event === undefined ? '' : String(event['type'] ?? '');
        if (['turn.succeeded', 'turn.failed', 'turn.cancelled', 'turn.interrupted'].includes(eventType)) return event ?? payload;
        continue;
      }
      if (String(payload['frame_id'] ?? '') !== frameId || String(payload['request_id'] ?? '') !== requestId) throw new Error('remote receipt frame mismatch');
    }
  }

  async close(): Promise<void> {
    await this.closeSocket();
    this.failPending();
  }

  private async open(url: string, relay: boolean): Promise<void> {
    let socket = webSocket.createWebSocket();
    this.socket = socket;
    socket.on('message', (error: Error, value: string | ArrayBuffer) => { if (error === null) this.receive(value); });
    socket.on('close', (error: Error, _value: webSocket.CloseResult) => { if (error === null) this.failPending(); });
    let options: webSocket.WebSocketRequestOptions = {};
    if (relay) options.header = { Authorization: `Bearer ${this.token}` };
    await socket.connect(url, options);
  }

  private async closeSocket(): Promise<void> {
    if (this.socket !== null) { let socket = this.socket; this.socket = null; try { await socket.close({ code: 1000, reason: 'closed by client' }); } catch (_) {} }
  }

  private async lanAuthorization(): Promise<void> {
    if (this.socket === null) throw new Error('Harmony socket is closed');
    let hello: Record<string, Object> = JSON.parse('{}') as Record<string, Object>; hello['type'] = 'hello'; hello['protocol_version'] = 'notemeld.lan.v1'; hello['controller_device_id'] = this.controllerId;
    await this.socket.send(JSON.stringify(hello));
    let challenge = JSON.parse(await this.nextMessage()) as Record<string, Object>;
    if (challenge['type'] !== 'challenge') throw new Error('LAN challenge rejected');
    let challengeID = String(challenge['challenge_id'] ?? ''); let value = String(challenge['challenge'] ?? '');
    let message = HarmonyRemoteTransport.utf8(`notemeld-lan-auth-v1\0${this.sessionId}\0${this.controllerId}\0${this.host.id}\0${challengeID}\0${value}`);
    let signature = HarmonyRemoteCrypto.base64(await HarmonyRemoteCrypto.sign(this.identity.pair, message));
    let proof: Record<string, Object> = JSON.parse('{}') as Record<string, Object>; proof['type'] = 'proof'; proof['challenge_id'] = challengeID; proof['challenge'] = value; proof['signature'] = signature;
    await this.socket.send(JSON.stringify(proof));
    let authorized = JSON.parse(await this.nextMessage()) as Record<string, Object>;
    if (authorized['type'] !== 'authorized' || authorized['session_id'] !== this.sessionId) throw new Error('LAN authorization rejected');
    this.authorityEpoch = Number(authorized['authority_epoch'] ?? 0); if (this.authorityEpoch < 1) throw new Error('invalid LAN authority epoch');
  }

  private async handshake(relay: boolean): Promise<void> {
    let ephemeral = await HarmonyRemoteCrypto.generateEphemeral();
    let publicKey = HarmonyRemoteCrypto.base64(ephemeral.publicKey);
    let signingBytes = HarmonyRemoteTransport.handshakeMessage(this.sessionId, this.controllerId, this.host.id, ephemeral.publicKey);
    let signature = HarmonyRemoteCrypto.base64(await HarmonyRemoteCrypto.sign(this.identity.pair, signingBytes));
    let offer: Record<string, Object> = JSON.parse('{}') as Record<string, Object>; offer['protocol_version'] = 'notemeld.e2ee.handshake.v1'; offer['session_id'] = this.sessionId; offer['sender_device_id'] = this.controllerId; offer['recipient_device_id'] = this.host.id; offer['ephemeral_public'] = publicKey; offer['signature'] = signature;
    let nonce = await HarmonyRemoteCrypto.random(12);
    let frame: Record<string, Object> = JSON.parse('{}') as Record<string, Object>; frame['authority_epoch'] = this.authorityEpoch; frame['frame_id'] = `${Date.now()}-handshake`; frame['frame_type'] = 'handshake'; frame['nonce'] = HarmonyRemoteCrypto.base64(nonce); frame['protocol_version'] = 'notemeld.sync.v1'; frame['recipient_device_id'] = this.host.id; frame['sender_device_id'] = this.controllerId; frame['sequence'] = 1; frame['session_id'] = this.sessionId; frame['ciphertext'] = HarmonyRemoteCrypto.base64(HarmonyRemoteTransport.utf8(JSON.stringify(offer)));
    if (this.socket === null) throw new Error('Harmony socket is closed');
    await this.socket.send(JSON.stringify(relay ? frame : offer));
    let response = JSON.parse(await this.nextMessage()) as Record<string, Object>;
    if (relay && response['frame_type'] !== 'handshake') throw new Error('Harmony relay handshake rejected');
    if (!relay && response['protocol_version'] !== 'notemeld.e2ee.handshake.v1') throw new Error('Harmony LAN handshake rejected');
    let peerEncoded = relay ? String(response['ciphertext'] ?? '') : '';
    let peer = relay ? JSON.parse(HarmonyRemoteTransport.text(HarmonyRemoteTransport.decode(peerEncoded))) as Record<string, Object> : response;
    if (peer.session_id !== this.sessionId || peer.sender_device_id !== this.host.id || peer.recipient_device_id !== this.controllerId) throw new Error('Harmony handshake endpoint mismatch');
    let peerPublic = HarmonyRemoteTransport.decode(String(peer.ephemeral_public ?? ''));
    let peerSignature = HarmonyRemoteTransport.decode(String(peer.signature ?? ''));
    if (!await HarmonyRemoteCrypto.verify(this.host.publicKey, peerSignature, HarmonyRemoteTransport.handshakeMessage(this.sessionId, this.host.id, this.controllerId, peerPublic))) throw new Error('Harmony handshake signature invalid');
    let shared = await HarmonyRemoteCrypto.derive(ephemeral, peerPublic);
    let firstId = this.controllerId < this.host.id ? this.controllerId : this.host.id;
    let firstPublic = firstId === this.controllerId ? ephemeral.publicKey : peerPublic;
    let secondId = firstId === this.controllerId ? this.host.id : this.controllerId;
    let secondPublic = firstId === this.controllerId ? peerPublic : ephemeral.publicKey;
    this.sessionKey = await HarmonyRemoteCrypto.hkdf(shared, HarmonyRemoteTransport.handshakeTranscript(this.sessionId, firstId, firstPublic, secondId, secondPublic));
  }

  private async decryptFrame(frame: Record<string, Object>): Promise<Record<string, Object>> {
    if (this.sessionKey === null) throw new Error('Harmony session key is unavailable');
    let ciphertext = String(frame['ciphertext'] ?? ''); let nonce = String(frame['nonce'] ?? '');
    if (ciphertext.length === 0 || nonce.length === 0) throw new Error('remote frame is missing encrypted payload');
    let metadata: Record<string, Object> = {};
    Object.keys(frame).forEach((key: string) => { if (key !== 'ciphertext') metadata[key] = frame[key]; });
    let plaintext = await HarmonyRemoteCrypto.decrypt(this.sessionKey, HarmonyRemoteTransport.decode(nonce), HarmonyRemoteTransport.decode(ciphertext), HarmonyRemoteTransport.utf8(HarmonyRemoteTransport.canonical(metadata)));
    return JSON.parse(HarmonyRemoteTransport.text(plaintext)) as Record<string, Object>;
  }

  private receive(value: string | ArrayBuffer): void {
    let text = typeof value === 'string' ? value : HarmonyRemoteTransport.text(new Uint8Array(value));
    let waiter = this.pending.shift();
    if (waiter !== undefined) waiter(text); else this.messages.push(text);
  }

  private nextMessage(): Promise<string> {
    let existing = this.messages.shift();
    if (existing !== undefined) return Promise.resolve(existing);
    return new Promise<string>((resolve: (value: string) => void) => this.pending.push(resolve));
  }

  private failPending(): void { while (this.pending.length > 0) { let waiter = this.pending.shift(); if (waiter !== undefined) waiter(JSON.stringify({ type: 'failed', error: 'socket closed' })); } }

  private static handshakeMessage(sessionId: string, sender: string, recipient: string, publicKey: Uint8Array): Uint8Array { return HarmonyRemoteTransport.concat(HarmonyRemoteTransport.utf8(`notemeld-e2ee-v1\0${sessionId}\0${sender}\0${recipient}\0`), publicKey); }
  private static handshakeTranscript(sessionId: string, first: string, firstPublic: Uint8Array, second: string, secondPublic: Uint8Array): Uint8Array { return HarmonyRemoteTransport.concat(HarmonyRemoteTransport.utf8(`notemeld-e2ee-transcript-v1\0${sessionId}\0${first}\0${second}\0`), firstPublic, secondPublic); }
  private static copy(value: Record<string, Object>): Record<string, Object> { let output: Record<string, Object> = JSON.parse('{}') as Record<string, Object>; Object.keys(value).forEach((key: string) => output[key] = value[key]); return output; }
  private static canonical(value: Record<string, Object>): string { let keys = Object.keys(value).sort(); let parts: string[] = []; keys.forEach((key: string) => parts.push(`${JSON.stringify(key)}:${JSON.stringify(value[key])}`)); return `{${parts.join(',')}}`; }
  private static concat(...parts: Uint8Array[]): Uint8Array { let total = 0; parts.forEach((part: Uint8Array) => total += part.length); let output = new Uint8Array(total); let offset = 0; parts.forEach((part: Uint8Array) => { output.set(part, offset); offset += part.length; }); return output; }
  private static utf8(value: string): Uint8Array { return new util.TextEncoder().encodeInto(value); }
  private static text(value: Uint8Array): string { return new util.TextDecoder().decodeWithStream(value); }
  private static escape(value: string): string { return encodeURIComponent(value); }
  private static websocketScheme(value: string): string { if (value.startsWith('https://')) return `wss://${value.substring(8)}`; if (value.startsWith('http://')) return `ws://${value.substring(7)}`; return value; }
  static decode(value: string): Uint8Array { let normalized = value.replace(/-/g, '+').replace(/_/g, '/') + '='.repeat((4 - value.length % 4) % 4); let alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/'; let bytes: number[] = []; let buffer = 0; let bits = 0; for (let index = 0; index < normalized.length; index += 1) { let current = normalized.charAt(index); if (current === '=') break; let digit = alphabet.indexOf(current); if (digit < 0) throw new Error('invalid base64'); buffer = (buffer << 6) | digit; bits += 6; if (bits >= 8) { bits -= 8; bytes.push((buffer >> bits) & 255); } } return new Uint8Array(bytes); }
}
