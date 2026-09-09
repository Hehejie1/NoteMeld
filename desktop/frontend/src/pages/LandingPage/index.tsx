import { useEffect, useRef, useState, type MouseEvent } from 'react'
import { Link } from 'react-router-dom'
import { openExternalUrl } from '@/utils/runtime'
import './landing.css'

const desktopDownloads = {
  appleSilicon: 'http://43.167.164.213/files/f_20260602_53c22160366f.dmg',
  intel: 'http://43.167.164.213/files/f_20260602_4d812951bf4c.dmg',
}

const sourceItems = [
  { kind: 'web', label: '网页', src: '/landing/source-web.png' },
  { kind: 'video', label: '视频', src: '/landing/source-video.png' },
  { kind: 'file', label: '文件', src: '/landing/source-file.png' },
  { kind: 'book', label: '书籍', src: '/landing/source-book.png' },
  { kind: 'audio', label: '录音', src: '/landing/source-audio.png' },
]

const heroBullets = [
  {
    title: '视频总结学习',
    description:
      '支持抖音、哔哩哔哩、快手、视频号和本地视频，把课程、访谈、案例与实操内容整理成可复习的总结笔记。',
  },
  {
    title: '沉淀为 Wiki',
    description: '每篇笔记继续抽取实体、概念、证据和关系，沉淀成可追溯、可复用的知识层。',
  },
  {
    title: '接到日常工具',
    description: '后续既可以在 NoteMeld 里继续对话，也可以通过 MCP 接入 Trae、Cursor 等日常工作流工具。',
  },
]

const supportCards = [
  {
    title: '短视频与课程总结',
    description: '把抖音、哔哩哔哩、快手、视频号和本地视频里的知识点，整理成适合学习和复盘的结构化笔记。',
  },
  {
    title: '网页与资料统一沉淀',
    description: '网页文章、本地文件和研究资料不再散落在不同工具里，而是进入同一个知识层持续累积。',
  },
  {
    title: 'AI 对话继续入库',
    description: '重要讨论、结论和推理过程可以继续沉淀，后面提问时直接建立在已有上下文之上。',
  },
]

const scenarioFlow = [
  {
    title: '导入内容',
    description: '从视频、网页、文件和 AI 对话开始，先把值得反复回看的内容收进来。',
  },
  {
    title: '总结笔记',
    description: 'Refine Engine 生成结构化总结笔记，方便学习、复盘和继续编辑。',
  },
  {
    title: 'Wiki 沉淀',
    description: '继续抽取实体、概念、证据和关系，把单条内容编译成可长期复用的知识层。',
  },
  {
    title: '对话 / MCP',
    description: '下一次继续研究时，既能直接对话提问，也能通过 MCP 把知识接入日常工具。',
  },
]

const scenarioCards = [
  {
    title: '课程学习',
    description: '把长视频、课程和讲座整理成真正能反复复习的学习资料。',
  },
  {
    title: '视频复盘',
    description: '把案例分析、操盘拆解和经验分享总结成后面还能继续追问的结论。',
  },
  {
    title: '专题研究',
    description: '持续跟踪某个主题时，把多条视频、网页和自己的思考接成一条研究链路。',
  },
  {
    title: '内容创作',
    description: '写文章、做分享或写方案时，直接回到自己的总结笔记和 Wiki 拿素材。',
  },
  {
    title: '团队知识沉淀',
    description: '把内部讨论、资料和外部内容整理为更容易查找和传递的知识资产。',
  },
  {
    title: '工具链接入',
    description: '通过对话和 MCP 把知识库带进 Trae、Cursor 等工作流工具，而不是每次重新搜索。',
  },
]

const featureCards = [
  {
    index: '01',
    title: '多源采集',
    description: '网页、视频、文件、AI 对话统一进入同一知识层，不再散落在不同平台。',
  },
  {
    index: '02',
    title: '结构化笔记',
    description: '自动生成可阅读、可编辑、可复盘的 Markdown，长内容也能稳定整理。',
  },
  {
    index: '03',
    title: 'Wiki-First',
    description: '不是堆原文再临时检索，而是把内容编译成长期可复用的知识层。',
  },
  {
    index: '04',
    title: '证据可追溯',
    description: '实体、概念、观点都能回到来源上下文，写作和决策时更有依据。',
  },
  {
    index: '05',
    title: '本地自托管',
    description: '数据保留在自己的机器上，SQLite 持久化，2C2G 小机器也能跑。',
  },
  {
    index: '06',
    title: '持续增长',
    description: '每一次阅读、观看、对话，都会继续丰富同一个个人知识网络。',
  },
]

const repoBadges = ['MIT License', 'React 19', 'FastAPI', 'Python 3.11+', 'Browser Extension', 'MVP']

type OrbitConfig = {
  width: number
  height: number
  centerX: number
  centerY: number
  radiusX: number
  radiusY: number
  coreRadius: number
  rotation: number
  shear: number
}

const degreesToRadians = (degrees: number) => degrees * (Math.PI / 180)
const ORBIT_VISUAL_TILT_DEGREES = -30
const ORBIT_SHEAR = 0.03

const getRotationForVisualTilt = (tiltDegrees: number, shear: number) => {
  return Math.atan(Math.tan(degreesToRadians(tiltDegrees)) + shear)
}

const createOrbitConfig = (element?: HTMLElement | null): OrbitConfig => {
  const rect = element?.getBoundingClientRect()
  const width = Math.max(1, rect?.width || 720)
  const height = Math.max(1, rect?.height || 540)

  return {
    width,
    height,
    centerX: width * 0.5,
    centerY: height * 0.515,
    radiusX: width * 0.4375,
    radiusY: height * 0.2815,
    coreRadius: Math.min(width, height) * 0.289,
    rotation: getRotationForVisualTilt(ORBIT_VISUAL_TILT_DEGREES, ORBIT_SHEAR),
    shear: ORBIT_SHEAR,
  }
}

const getOrbitPoint = (
  config: OrbitConfig,
  angle: number,
  radiusX = config.radiusX,
  radiusY = config.radiusY,
) => {
  const localX = Math.cos(angle) * radiusX
  const localY = Math.sin(angle) * radiusY
  const rotatedX = localX * Math.cos(config.rotation) - localY * Math.sin(config.rotation)
  const rotatedY = localX * Math.sin(config.rotation) + localY * Math.cos(config.rotation)

  return {
    x: config.centerX + rotatedX,
    y: config.centerY + rotatedY - rotatedX * config.shear,
    depth: (localY / radiusY + 1) / 2,
  }
}

const createOrbitPath = (config: OrbitConfig, radiusX: number, radiusY: number) => {
  const points = Array.from({ length: 121 }, (_, index) => {
    const angle = (index / 120) * Math.PI * 2
    const point = getOrbitPoint(config, angle, radiusX, radiusY)
    return `${index === 0 ? 'M' : 'L'} ${point.x.toFixed(2)} ${point.y.toFixed(2)}`
  })

  return `${points.join(' ')} Z`
}

const buildOrbitPaths = (config: OrbitConfig) => ({
  viewBox: `0 0 ${config.width.toFixed(2)} ${config.height.toFixed(2)}`,
  outer: createOrbitPath(config, config.radiusX, config.radiusY),
  inner: createOrbitPath(config, config.radiusX * 0.72, config.radiusY * 0.64),
})

const initialOrbitPaths = buildOrbitPaths(createOrbitConfig())

const LandingPage = () => {
  const visualRef = useRef<HTMLDivElement | null>(null)
  const orbitRef = useRef<HTMLDivElement | null>(null)
  const [orbitPaths, setOrbitPaths] = useState(initialOrbitPaths)
  const githubUrl = 'https://github.com/Hehejie1/NoteMeld'

  const handleOpenGithub = async (event: MouseEvent<HTMLAnchorElement>) => {
    event.preventDefault()
    await openExternalUrl(githubUrl)
  }

  useEffect(() => {
    const visual = visualRef.current
    const root = orbitRef.current
    if (!visual || !root) return

    const cards = Array.from(root.querySelectorAll<HTMLElement>('.landing-floating-source'))
    const streams = Array.from(root.querySelectorAll<HTMLElement>('.landing-ingest-stream'))
    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    const speed = reducedMotion ? 0 : 0.00022
    let orbitConfig = createOrbitConfig(visual)
    let frameId = 0
    let startTime = performance.now()
    let lastOrbitTime = startTime

    const syncOrbitGuides = () => {
      orbitConfig = createOrbitConfig(visual)
      setOrbitPaths(buildOrbitPaths(orbitConfig))
    }

    const updateOrbit = (now: number) => {
      lastOrbitTime = now
      const progress = (now - startTime) * speed

      cards.forEach((card, index) => {
        const angle = progress + (index / cards.length) * Math.PI * 2 - Math.PI / 2
        const { x, y, depth } = getOrbitPoint(orbitConfig, angle)
        const scale = 0.74 + depth * 0.22
        const zIndex = Math.round(40 + depth * 30)

        card.style.left = `${x}px`
        card.style.top = `${y}px`
        card.style.zIndex = `${zIndex}`
        card.style.transform = 'translate(-50%, -50%)'
        card.style.setProperty('--source-scale', `${scale}`)
        card.style.opacity = `${0.82 + depth * 0.18}`

        const stream = streams[index]
        if (stream) {
          const deltaX = orbitConfig.centerX - x
          const deltaY = orbitConfig.centerY - y
          const length = Math.max(0, Math.hypot(deltaX, deltaY) - orbitConfig.coreRadius)
          const streamAngle = Math.atan2(deltaY, deltaX) * (180 / Math.PI)

          stream.style.left = `${x}px`
          stream.style.top = `${y}px`
          stream.style.width = `${length}px`
          stream.style.setProperty('--stream-length', `${length}px`)
          stream.style.zIndex = `${zIndex - 1}`
          stream.style.transform = `rotate(${streamAngle}deg)`
        }
      })

      if (!reducedMotion) {
        frameId = requestAnimationFrame(updateOrbit)
      }
    }

    syncOrbitGuides()
    updateOrbit(startTime)

    const resizeObserver = new ResizeObserver(() => {
      syncOrbitGuides()
      updateOrbit(lastOrbitTime)
    })
    resizeObserver.observe(visual)

    if (!reducedMotion) {
      frameId = requestAnimationFrame(updateOrbit)
    }

    return () => {
      cancelAnimationFrame(frameId)
      resizeObserver.disconnect()
      startTime = 0
    }
  }, [])

  return (
    <div className="landing-page">
      <header className="landing-nav">
        <Link to="/" className="landing-brand" aria-label="NoteMeld 首页">
          <img src="/notemeld-logo.png" alt="" className="landing-brand-icon" />
          <span className="landing-brand-copy">
            <strong>NoteMeld</strong>
            <small>源知库 · 你的专属知识库</small>
          </span>
        </Link>
        <div className="landing-nav-actions">
          <a
            href={githubUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="landing-nav-link"
            onClick={handleOpenGithub}
          >
            GitHub
          </a>
          <Link to="/new" className="landing-nav-cta">
            进入工作台
          </Link>
        </div>
      </header>

      <section className="landing-download-strip" aria-label="桌面端下载">
        <span className="landing-download-label">桌面端下载</span>
        <a href={desktopDownloads.appleSilicon} className="landing-download-link">
          Apple Silicon / arm64
        </a>
        <a href={desktopDownloads.intel} className="landing-download-link">
          Intel / x64
        </a>
      </section>

      <section className="landing-section landing-hero">
        <div className="landing-hero-layout">
          <div className="landing-hero-copy">
            <h1 className="landing-headline">真正有价值的内容，不该只被总结一次</h1>
            <div className="landing-hero-points">
              {heroBullets.map(item => (
                <div className="landing-hero-point" key={item.title}>
                  <span />
                  <p>
                    <strong>{item.title}</strong>
                    {item.description}
                  </p>
                </div>
              ))}
            </div>
          </div>

          <div className="landing-hero-visual" aria-hidden="true">
            <div className="landing-knowledge-visual" ref={visualRef}>
              <svg className="landing-orbit-guides" viewBox={orbitPaths.viewBox} preserveAspectRatio="none">
                <path className="landing-orbit-guide landing-orbit-guide--outer" d={orbitPaths.outer} />
                <path className="landing-orbit-guide landing-orbit-guide--inner" d={orbitPaths.inner} />
              </svg>

              <div className="landing-source-orbit landing-source-orbit--outer" ref={orbitRef}>
                {sourceItems.map((item, index) => (
                  <div
                    className={`landing-floating-source landing-floating-source--${index + 1} landing-source-${item.kind}`}
                    key={item.label}
                  >
                    <div className="landing-source-card">
                      <img src={item.src} alt="" />
                      <span>{item.label}</span>
                    </div>
                  </div>
                ))}

                {sourceItems.map(item => (
                  <div className="landing-ingest-stream" key={`${item.label}-stream`}>
                    <span />
                    <span />
                    <span />
                  </div>
                ))}
              </div>

              <div className="landing-library-card">
                <div className="landing-library-glow" />
                <img src="/landing/hero-core.png" alt="" className="landing-library-image" />
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="landing-section landing-scenario-section">
        <div className="landing-section-heading">
          <div className="landing-kicker">Scenarios & Flow</div>
          <h2>先把内容总结清楚，再让它进入你的 Wiki、对话和日常工作流。</h2>
          <p className="landing-scenario-intro">
            这不是只做一次视频总结，而是把抖音、哔哩哔哩、快手、视频号、本地视频，以及网页、文件、AI
            对话接成一条长期可复用的知识链路。
          </p>
        </div>

        <div className="landing-scenario-overview">
          <div className="landing-scenario-featured">
            <span className="landing-scenario-eyebrow">支持哪些内容</span>
            <h3>从短视频学习到专题研究，都可以进入同一个知识层。</h3>
            <p>
              NoteMeld 不是第二个收藏夹，而是一个把输入内容继续变成总结笔记、Wiki 和后续可调用上下文的个人研究台。
            </p>
          </div>
          <div className="landing-usage-card">
            <span className="landing-scenario-eyebrow">使用端</span>
            <h3>不止在网页里看，还能继续拿来用。</h3>
            <div className="landing-usage-list">
              <div className="landing-usage-item">
                <strong>对话</strong>
                <span>继续围绕同一主题提问、追问、复盘。</span>
              </div>
              <div className="landing-usage-item">
                <strong>MCP</strong>
                <span>接入 Trae、Cursor 和日常工具，把你的知识库带进工作流。</span>
              </div>
            </div>
          </div>
        </div>

        <div className="landing-support-grid">
          {supportCards.map(card => (
            <article key={card.title} className="landing-support-card">
              <span className="landing-scenario-eyebrow">内容来源</span>
              <h3>{card.title}</h3>
              <p>{card.description}</p>
            </article>
          ))}
        </div>

        <div className="landing-flow-card">
          <div className="landing-flow-header">
            <span className="landing-scenario-eyebrow">产品流程</span>
            <h3>导入内容 -&gt; 总结笔记 -&gt; Wiki -&gt; 对话 / MCP</h3>
            <p>
              参考 LLM Wiki 的方法论，NoteMeld 会先把原始内容转成结构化总结笔记，再继续沉淀为可检索、可追问、可复用的知识层。
            </p>
          </div>
          <div className="landing-flow-strip">
            {scenarioFlow.map(step => (
              <article key={step.title} className="landing-flow-step">
                <span className="landing-flow-index">{scenarioFlow.indexOf(step) + 1}</span>
                <h4>{step.title}</h4>
                <p>{step.description}</p>
              </article>
            ))}
          </div>
        </div>

        <div className="landing-scenario-grid">
          {scenarioCards.map(card => (
            <article key={card.title} className="landing-scenario-card">
              <h3>{card.title}</h3>
              <p>{card.description}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="landing-section landing-feature-section">
        <div className="landing-section-heading">
          <div className="landing-kicker">为什么是 NoteMeld</div>
          <h2>不是保存更多资料，而是沉淀可调用的认知资产。</h2>
        </div>
        <div className="landing-feature-grid">
          {featureCards.map(card => (
            <div key={card.title} className="landing-feature-card">
              <div className="landing-feature-index">{card.index}</div>
              <h3>{card.title}</h3>
              <p>{card.description}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="landing-section landing-repo-section">
        <div className="landing-repo-card">
          <div>
            <div className="landing-kicker">OPEN SOURCE</div>
            <h2>NoteMeld on GitHub</h2>
            <p>
              自托管 AI 知识工作台。前端基于 React 19，后端基于 FastAPI，支持浏览器扩展、
              多模型 Provider、本地持久化与 Wiki 知识沉淀。
            </p>
            <div className="landing-repo-badges">
              {repoBadges.map(badge => (
                <span key={badge}>{badge}</span>
              ))}
            </div>
          </div>
          <a
            href={githubUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="landing-repo-link"
            onClick={handleOpenGithub}
          >
            打开 GitHub
          </a>
        </div>
      </section>

      <footer className="landing-footer">NoteMeld · More Than Notes</footer>
    </div>
  )
}

export default LandingPage
