export interface ProviderTemplate {
  key?: string
  name: string
  logo: string
  baseUrl: string
}

export const providerTemplates: ProviderTemplate[] = [
  {
    key: 'volcengine',
    name: '火山引擎',
    logo: 'Volcengine',
    baseUrl: 'https://ark.cn-beijing.volces.com/api/v3',
  },
  {
    key: 'ollama',
    name: 'ollama',
    logo: 'Ollama',
    baseUrl: 'http://127.0.0.1:11434/v1',
  },
  {
    key: 'deepseek',
    name: 'DeepSeek',
    logo: 'DeepSeek',
    baseUrl: 'https://api.deepseek.com',
  },
  {
    key: 'qwen',
    name: 'Qwen',
    logo: 'Qwen',
    baseUrl: 'https://dashscope.aliyuncs.com/compatible-mode/v1',
  },
  {
    key: 'freemodel',
    name: 'FreeModel',
    logo: 'FreeModel',
    baseUrl: 'https://api.freemodel.dev/v1',
  },
  {
    key: 'openai',
    name: 'OpenAI',
    logo: 'OpenAI',
    baseUrl: 'https://api.openai.com/v1',
  },
  {
    key: 'gemini',
    name: 'Gemini',
    logo: 'Gemini',
    baseUrl: 'https://generativelanguage.googleapis.com/v1beta/openai/',
  },
  {
    key: 'groq',
    name: 'Groq',
    logo: 'Groq',
    baseUrl: 'https://api.groq.com/openai/v1',
  },
]

export const mergeProviderTemplates = (
  builtinTemplates: ProviderTemplate[],
  savedTemplates: ProviderTemplate[],
): ProviderTemplate[] => {
  const templatesByName = new Map<string, ProviderTemplate>()
  builtinTemplates.forEach(template => {
    templatesByName.set(template.name.toLowerCase(), template)
  })
  savedTemplates.forEach(template => {
    templatesByName.set(template.name.toLowerCase(), template)
  })
  return Array.from(templatesByName.values())
}
