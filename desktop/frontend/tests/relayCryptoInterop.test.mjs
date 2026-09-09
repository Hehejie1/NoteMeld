import assert from 'node:assert/strict'
import { webcrypto } from 'node:crypto'
import fs from 'node:fs'
import test from 'node:test'


function decode(value) {
  return Buffer.from(value.replace(/-/g, '+').replace(/_/g, '/'), 'base64')
}


test('WebCrypto decrypts the canonical Python AES-GCM relay fixture', async () => {
  const fixture = JSON.parse(fs.readFileSync(new URL('../../../tests/fixtures/relay-aes-gcm-v1.json', import.meta.url), 'utf8'))
  const { ciphertext: _ciphertext, ...metadata } = fixture.frame
  const associatedData = JSON.stringify(metadata, Object.keys(metadata).sort())
  assert.equal(associatedData, fixture.associated_data)

  const key = await webcrypto.subtle.importKey('raw', decode(fixture.key), 'AES-GCM', false, ['decrypt'])
  const plaintext = await webcrypto.subtle.decrypt(
    {
      name: 'AES-GCM',
      iv: decode(fixture.frame.nonce),
      additionalData: new TextEncoder().encode(associatedData),
    },
    key,
    decode(fixture.frame.ciphertext),
  )
  assert.equal(new TextDecoder().decode(plaintext), fixture.plaintext)
})
