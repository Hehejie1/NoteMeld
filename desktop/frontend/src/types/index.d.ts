export interface IProvider {
  id: string
  name: string
  logo: string
  /** @deprecated 安全出口不再回显明文，仅旧数据兜底；编辑时以 hasApiKey 判断是否已存密钥 */
  apiKey?: string
  baseUrl: string
  enabled: number
  // notemeld.model-add.v1 两级协议新增字段
  displayName?: string
  vendorId?: string
  protocol?: string
  authType?: string
  hasApiKey?: boolean
  credentialStatus?: 'saved' | 'missing' | string
  apiKeyMasked?: string
  createdAt?: string
}
export interface IResponse<T> {
  code: number
  data:T
  msg: string
}
