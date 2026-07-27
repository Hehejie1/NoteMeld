import type { FC, MouseEvent, ReactNode } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { ExternalLink } from 'lucide-react'
import { openExternalUrl } from '@/utils/runtime'

interface ChatMarkdownProps {
  content: string
}

const renderInlineChildren = (children: ReactNode) => children

const openChatExternalLink = (event: MouseEvent<HTMLAnchorElement>, href?: string) => {
  if (!href?.startsWith('http')) return
  event.preventDefault()
  openExternalUrl(href).catch(error => {
    console.warn('failed to open chat markdown link', error)
  })
}

const ChatMarkdown: FC<ChatMarkdownProps> = ({ content }) => {
  return (
    <div className="chat-markdown min-w-0 max-w-full overflow-hidden break-words text-[13px] leading-6">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          h1: ({ children }) => (
            <h1 className="mt-3 mb-1.5 text-[15px] font-semibold tracking-tight first:mt-0">
              {children}
            </h1>
          ),
          h2: ({ children }) => (
            <h2 className="mt-3 mb-1.5 text-[14px] font-semibold tracking-tight first:mt-0">
              {children}
            </h2>
          ),
          h3: ({ children }) => (
            <h3 className="mt-2.5 mb-1 text-[13px] font-semibold first:mt-0">{children}</h3>
          ),
          p: ({ children }) => <p className="my-1.5 first:mt-0 last:mb-0">{children}</p>,
          ul: ({ children }) => <ul className="my-1.5 ml-4.5 list-disc space-y-0.5">{children}</ul>,
          ol: ({ children }) => <ol className="my-1.5 ml-4.5 list-decimal space-y-0.5">{children}</ol>,
          li: ({ children }) => <li>{children}</li>,
          blockquote: ({ children }) => (
            <blockquote className="my-2 border-l-2 border-border-subtle/70 pl-2.5 text-on-surface-variant">
              {children}
            </blockquote>
          ),
          table: ({ children }) => (
            <div className="my-2 max-w-full overflow-x-auto rounded-md border border-border-subtle/50 bg-white/70">
              <table className="min-w-full border-collapse text-left text-[12px] leading-5">
                {children}
              </table>
            </div>
          ),
          img: ({ src, alt }) => (
            <img
              src={src || ''}
              alt={alt || ''}
              className="my-2 h-auto max-w-full rounded-lg object-contain"
            />
          ),
          thead: ({ children }) => <thead className="bg-surface-container/60">{children}</thead>,
          th: ({ children }) => (
            <th className="border border-border-subtle/50 px-2 py-1 font-medium text-on-surface">
              {children}
            </th>
          ),
          td: ({ children }) => (
            <td className="border border-border-subtle/40 px-2 py-1 text-on-surface-variant">
              {children}
            </td>
          ),
          code: ({ inline, children }) =>
            inline ? (
              <code className="rounded-md bg-surface-container/80 px-1 py-0.5 font-mono text-[11px] text-on-surface">
                {renderInlineChildren(children)}
              </code>
            ) : (
              <code className="block max-w-full overflow-x-auto rounded-md border border-border-subtle/50 bg-surface-container/80 px-2.5 py-2 font-mono text-[11px] leading-5 text-on-surface">
                {renderInlineChildren(children)}
              </code>
            ),
          pre: ({ children }) => <pre className="my-2 max-w-full overflow-x-auto">{children}</pre>,
          a: ({ href, children }) => (
            <a
              href={href}
              onClick={event => openChatExternalLink(event, href)}
              rel="noopener noreferrer"
              className="inline-flex min-w-0 max-w-full items-center gap-1 break-all text-primary underline decoration-primary/50 underline-offset-3"
            >
              {children}
              {href?.startsWith('http') && <ExternalLink className="h-3 w-3" />}
            </a>
          ),
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  )
}

export default ChatMarkdown
