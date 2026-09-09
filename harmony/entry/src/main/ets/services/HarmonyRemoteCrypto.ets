import cryptoFramework from '@ohos.security.cryptoFramework';

/**
 * Harmony implementation of the cross-platform NoteMeld E2EE primitives.
 *
 * Keys are kept as CryptoFramework objects while in use. Only the key-spec
 * integers are persisted by the caller through the platform preference store;
 * no private key is written to a normal file or sent to Cloud.
 */
export interface HarmonyKeyPair {
  pair: cryptoFramework.KeyPair;
  publicKey: Uint8Array;
}

export interface HarmonyEphemeralKeyPair extends HarmonyKeyPair {
  privateKey: cryptoFramework.PriKey;
}

export interface PersistedEd25519Key {
  privateSpec: string;
  publicSpec: string;
}

export interface EncryptedPayload {
  nonce: Uint8Array;
  ciphertext: Uint8Array;
}

export class HarmonyRemoteCrypto {
  static base64(value: Uint8Array): string {
    let alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/';
    let result = '';
    for (let index = 0; index < value.length; index += 3) {
      let first = value[index];
      let second = index + 1 < value.length ? value[index + 1] : 0;
      let third = index + 2 < value.length ? value[index + 2] : 0;
      result += alphabet.charAt(first >> 2);
      result += alphabet.charAt(((first & 3) << 4) | (second >> 4));
      result += index + 1 < value.length ? alphabet.charAt(((second & 15) << 2) | (third >> 6)) : '=';
      result += index + 2 < value.length ? alphabet.charAt(third & 63) : '=';
    }
    return result.replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
  }

  static async generateIdentity(): Promise<HarmonyKeyPair> {
    return HarmonyRemoteCrypto.generatePair('ED25519', cryptoFramework.AsyKeySpecItem.ED25519_PK_BN);
  }

  static async generateEphemeral(): Promise<HarmonyEphemeralKeyPair> {
    let generated = await cryptoFramework.createAsyKeyGenerator('X25519').generateKeyPair();
    return { pair: generated, privateKey: generated.priKey, publicKey: HarmonyRemoteCrypto.specBytes(generated.pubKey.getAsyKeySpec(cryptoFramework.AsyKeySpecItem.X25519_PK_BN)) };
  }

  static async restoreIdentity(saved: PersistedEd25519Key): Promise<HarmonyKeyPair> {
    let generator = cryptoFramework.createAsyKeyGeneratorBySpec({
      algName: 'ED25519',
      specType: cryptoFramework.AsyKeySpecType.KEY_PAIR_SPEC,
      sk: BigInt(saved.privateSpec),
      pk: BigInt(saved.publicSpec)
    } as cryptoFramework.ED25519KeyPairSpec);
    let pair = await generator.generateKeyPair();
    return { pair, publicKey: HarmonyRemoteCrypto.specBytes(BigInt(saved.publicSpec)) };
  }

  static persistedIdentity(pair: HarmonyKeyPair): PersistedEd25519Key {
    return {
      privateSpec: String(pair.pair.priKey.getAsyKeySpec(cryptoFramework.AsyKeySpecItem.ED25519_SK_BN)),
      publicSpec: String(pair.pair.pubKey.getAsyKeySpec(cryptoFramework.AsyKeySpecItem.ED25519_PK_BN))
    };
  }

  static async sign(pair: cryptoFramework.KeyPair, data: Uint8Array): Promise<Uint8Array> {
    let signer = cryptoFramework.createSign('ED25519');
    await signer.init(pair.priKey);
    let signature = await signer.sign({ data });
    return signature.data;
  }

  static async verify(publicKey: Uint8Array, signature: Uint8Array, data: Uint8Array): Promise<boolean> {
    let generator = cryptoFramework.createAsyKeyGeneratorBySpec({
      algName: 'ED25519',
      specType: cryptoFramework.AsyKeySpecType.PUBLIC_KEY_SPEC,
      pk: HarmonyRemoteCrypto.specValue(publicKey)
    } as cryptoFramework.ED25519PubKeySpec);
    let publicPart = await generator.generatePubKey();
    let verifier = cryptoFramework.createVerify('ED25519');
    await verifier.init(publicPart);
    return await verifier.verify({ data }, { data: signature });
  }

  static async derive(ephemeral: HarmonyEphemeralKeyPair, peerPublic: Uint8Array): Promise<Uint8Array> {
    let generator = cryptoFramework.createAsyKeyGeneratorBySpec({
      algName: 'X25519',
      specType: cryptoFramework.AsyKeySpecType.PUBLIC_KEY_SPEC,
      pk: HarmonyRemoteCrypto.specValue(peerPublic)
    } as cryptoFramework.X25519PubKeySpec);
    let publicPart = await generator.generatePubKey();
    let agreement = cryptoFramework.createKeyAgreement('X25519');
    let shared = await agreement.generateSecret(ephemeral.privateKey, publicPart);
    return shared.data;
  }

  static async hkdf(shared: Uint8Array, info: Uint8Array): Promise<Uint8Array> {
    let kdf = cryptoFramework.createKdf('HKDF');
    let spec: cryptoFramework.HKDFSpec = { algName: 'HKDF', key: shared, salt: new Uint8Array(0), info, keySize: 32 };
    let result = await kdf.generateSecret(spec);
    return result.data;
  }

  static async random(length: number): Promise<Uint8Array> {
    return (await cryptoFramework.createRandom().generateRandom(length)).data;
  }

  static async encrypt(key: Uint8Array, plaintext: Uint8Array, aad: Uint8Array, suppliedNonce?: Uint8Array): Promise<EncryptedPayload> {
    let nonce = suppliedNonce ?? await HarmonyRemoteCrypto.random(12);
    let symmetric = await cryptoFramework.createSymKeyGenerator('AES256').convertKey({ data: key });
    let cipher = cryptoFramework.createCipher('AES256|GCM|NoPadding');
    let params: cryptoFramework.GcmParamsSpec = { algName: 'GCM', iv: { data: nonce }, aad: { data: aad }, authTag: { data: new Uint8Array(0) } };
    await cipher.init(cryptoFramework.CryptoMode.ENCRYPT_MODE, symmetric, params);
    let result = await cipher.doFinal({ data: plaintext });
    let tag = params.authTag.data;
    return { nonce, ciphertext: HarmonyRemoteCrypto.join(result.data, tag) };
  }

  static async decrypt(key: Uint8Array, nonce: Uint8Array, ciphertext: Uint8Array, aad: Uint8Array): Promise<Uint8Array> {
    if (ciphertext.length < 16) throw new Error('ciphertext is too short');
    let symmetric = await cryptoFramework.createSymKeyGenerator('AES256').convertKey({ data: key });
    let cipher = cryptoFramework.createCipher('AES256|GCM|NoPadding');
    let params: cryptoFramework.GcmParamsSpec = { algName: 'GCM', iv: { data: nonce }, aad: { data: aad }, authTag: { data: ciphertext.slice(ciphertext.length - 16) } };
    await cipher.init(cryptoFramework.CryptoMode.DECRYPT_MODE, symmetric, params);
    let result = await cipher.doFinal({ data: ciphertext.slice(0, ciphertext.length - 16) });
    return result.data;
  }

  private static async generatePair(algorithm: string, publicSpec: cryptoFramework.AsyKeySpecItem): Promise<HarmonyKeyPair> {
    let pair = await cryptoFramework.createAsyKeyGenerator(algorithm).generateKeyPair();
    return { pair, publicKey: HarmonyRemoteCrypto.specBytes(pair.pubKey.getAsyKeySpec(publicSpec)) };
  }

  private static specBytes(value: bigint | string | number): Uint8Array {
    return HarmonyRemoteCrypto.bytesSpec(BigInt(value));
  }

  private static bytesSpec(value: bigint): Uint8Array {
    let output = new Uint8Array(32);
    let current = value;
    for (let index = 31; index >= 0; index -= 1) {
      output[index] = Number(current & BigInt(255));
      current >>= BigInt(8);
    }
    return output;
  }

  private static specValue(value: Uint8Array): bigint {
    let result = BigInt(0);
    value.forEach((item: number) => { result = (result << BigInt(8)) | BigInt(item); });
    return result;
  }

  private static join(first: Uint8Array, second: Uint8Array): Uint8Array {
    let output = new Uint8Array(first.length + second.length);
    output.set(first, 0); output.set(second, first.length); return output;
  }
}
