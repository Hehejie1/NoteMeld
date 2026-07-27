import { useEffect, useRef, useState } from 'react'
import { Markmap } from 'markmap-view'
import { transformer } from '@/lib/markmap.ts'
import JSZip from 'jszip'
import { Brain, Expand, Image as ImageIcon, Minimize2 } from 'lucide-react'
import { getMarkmapToolbarButtons } from '@/pages/HomePage/markmapUiHelpers'

export interface MarkmapEditorProps {
  /** 要渲染的 Markdown 文本 */
  value: string
  /** 内容变化时的回调 */
  onChange: (value: string) => void
  /** 容器 SVG 的高度，默认为 600px */
  height?: string
  /** 文档标题，用于导出HTML时的文件名 */
  title?: string
}

export default function MarkmapEditor({
  value,
  onChange: _onChange,
  height = '600px',
  title = 'mindmap',
}: MarkmapEditorProps) {
  const svgRef = useRef<SVGSVGElement>(null)
  const mmRef = useRef<Markmap | undefined>()

  // 用于跟踪是否处于全屏状态
  const [isFullscreen, setIsFullscreen] = useState(false)

  // 监听全屏状态变化
  useEffect(() => {
    const handler = () => {
      setIsFullscreen(!!document.fullscreenElement)
    }
    document.addEventListener('fullscreenchange', handler)
    return () => {
      document.removeEventListener('fullscreenchange', handler)
    }
  }, [])

  // 进入全屏
  const enterFullscreen = () => {
    const el = svgRef.current?.parentElement
    if (el && el.requestFullscreen) {
      el.requestFullscreen()
    }
  }

  // 退出全屏
  const exitFullscreen = () => {
    if (document.exitFullscreen) {
      document.exitFullscreen()
    }
  }
  
  // 导出XMind格式思维导图
  const exportXMind = async () => {
    try {
      const { root } = transformer.transform(value);

      // 生成唯一ID
      const generateId = () => Math.random().toString(36).substring(2, 15);

      // 解码HTML实体（如 &#x5b9e; -> 实，&#12345; -> 对应字符）
      const decodeHtmlEntities = (text: string): string => {
        if (!text) return text;

        // 首先手动处理十六进制数字实体 &#xHHHH;
        let decoded = text.replace(/&#x([0-9a-fA-F]+);/g, (_, hex) => {
          return String.fromCodePoint(parseInt(hex, 16));
        });

        // 处理十进制数字实体 &#DDDD;
        decoded = decoded.replace(/&#(\d+);/g, (_, dec) => {
          return String.fromCodePoint(parseInt(dec, 10));
        });

        // 使用textarea处理命名实体（如 &amp; &lt; &gt; 等）
        const textarea = document.createElement('textarea');
        textarea.innerHTML = decoded;
        return textarea.value;
      };

      // 清理HTML标签，只保留纯文本
      const stripHtml = (html: string): string => {
        if (!html) return html;
        // 先解码HTML实体
        let text = decodeHtmlEntities(html);
        // 移除HTML标签
        const div = document.createElement('div');
        div.innerHTML = text;
        return div.textContent || div.innerText || text;
      };

      // 将 markmap 节点转换为 XMind 节点格式
      const convertToXMindNode = (node: any, isRoot = false): any => {
        const rawTitle = node.content || node.payload?.content || '未命名';
        const xmindNode: any = {
          id: generateId(),
          class: isRoot ? 'topic' : 'topic',
          title: stripHtml(rawTitle),
        };

        if (node.children && node.children.length > 0) {
          xmindNode.children = {
            attached: node.children.map((child: any) => convertToXMindNode(child, false))
          };
        }

        return xmindNode;
      };

      const rootTopic = convertToXMindNode(root, true);
      const sheetId = generateId();

      // XMind content.json 结构
      const content = [{
        id: sheetId,
        class: 'sheet',
        title: stripHtml(title) || '思维导图',
        rootTopic: rootTopic,
        topicPositioning: 'fixed'
      }];

      // XMind metadata.json
      const metadata = {
        creator: {
          name: 'NoteMeld',
          version: '1.0.0'
        }
      };

      // XMind manifest.json
      const manifest = {
        'file-entries': {
          'content.json': {},
          'metadata.json': {}
        }
      };

      // 使用 JSZip 创建 .xmind 文件
      // 直接传入字符串，JSZip会自动处理UTF-8编码
      const zip = new JSZip();
      zip.file('content.json', JSON.stringify(content, null, 2));
      zip.file('metadata.json', JSON.stringify(metadata, null, 2));
      zip.file('manifest.json', JSON.stringify(manifest, null, 2));

      // 生成 ZIP 并下载
      const blob = await zip.generateAsync({ type: 'blob' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${title || 'mindmap'}.xmind`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (error) {
      console.error('导出XMind失败:', error);
    }
  };

  // 导出PNG思维导图
  const exportPng = async () => {
    try {
      if (!svgRef.current || !mmRef.current) return;

      const svgEl = svgRef.current;
      const mm = mmRef.current;

      // 先调用fit()确保显示完整的思维导图内容
      await mm.fit();
      // 等待渲染完成
      await new Promise(resolve => setTimeout(resolve, 100));
      
      // 获取SVG实际尺寸
      const svgWidth = svgEl.width.baseVal.value || svgEl.clientWidth || 800;
      const svgHeight = svgEl.height.baseVal.value || svgEl.clientHeight || 600;
      
      // 设置足够大的缩放比例以确保高清输出
      const scale = 3;
      
      // 克隆SVG以避免修改原始SVG
      const clonedSvg = svgEl.cloneNode(true) as SVGSVGElement;
      
      // 设置SVG的背景为白色
      const style = document.createElementNS('http://www.w3.org/2000/svg', 'style');
      style.textContent = 'svg { background-color: white; }';
      clonedSvg.insertBefore(style, clonedSvg.firstChild);
      
      // 确保SVG有正确的命名空间
      clonedSvg.setAttribute('xmlns', 'http://www.w3.org/2000/svg');
      clonedSvg.setAttribute('width', svgWidth.toString());
      clonedSvg.setAttribute('height', svgHeight.toString());
      
      // 将SVG转换为Data URI (避免使用Blob URL来解决跨域问题)
      const svgData = new XMLSerializer().serializeToString(clonedSvg);
      const svgBase64 = btoa(unescape(encodeURIComponent(svgData)));
      const dataUri = `data:image/svg+xml;base64,${svgBase64}`;
      
      // 创建Canvas
      const canvas = document.createElement('canvas');
      canvas.width = svgWidth * scale;
      canvas.height = svgHeight * scale;
      
      // 获取上下文并设置白色背景
      const ctx = canvas.getContext('2d');
      if (!ctx) {
        throw new Error('无法获取Canvas上下文');
      }
      
      // 设置白色背景
      ctx.fillStyle = '#FFFFFF';
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      
      // 创建Image对象
      const img = new Image();
      
      // 当图片加载完成后，在Canvas上绘制并导出
      img.onload = () => {
        try {
          // 应用缩放
          ctx.setTransform(scale, 0, 0, scale, 0, 0);
          
          // 绘制SVG
          ctx.drawImage(img, 0, 0);
          
          // 重置变换
          ctx.setTransform(1, 0, 0, 1, 0, 0);
          
          // 将Canvas转换为PNG Blob
          canvas.toBlob((blob) => {
            if (blob) {
              // 创建下载链接
              const url = URL.createObjectURL(blob);
              const a = document.createElement('a');
              a.href = url;
              a.download = `${title || 'mindmap'}.png`;
              document.body.appendChild(a);
              a.click();
              document.body.removeChild(a);
              URL.revokeObjectURL(url);
            } else {
              console.error('无法创建Blob对象');
            }
          }, 'image/png');
        } catch (err) {
          console.error('Canvas处理失败:', err);
        }
      };
      
      // 设置图片加载错误处理
      img.onerror = (error) => {
        console.error('导出PNG失败（图片加载错误）:', error);
      };
      
      // 开始加载SVG图像 (使用Data URI而不是Blob URL)
      img.src = dataUri;
      
    } catch (error) {
      console.error('导出PNG失败:', error);
    }
  };

  // 初始化 Markmap 实例
  useEffect(() => {
    if (!svgRef.current || mmRef.current) return
    const mm = Markmap.create(svgRef.current)
    mmRef.current = mm
  }, [])

  // 当 value 变化时，重新渲染数据
  useEffect(() => {
    const mm = mmRef.current
    if (!mm) return
    const { root } = transformer.transform(value)
    mm.setData(root).then(() => mm.fit())
  }, [value])

  // 文本输入变化回调（如果你自行添加 textarea 编辑区）
  // const handleChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
  //   onChange(e.target.value)
  // }

  const buttons = getMarkmapToolbarButtons(isFullscreen)
  const iconMap = {
    xmind: Brain,
    png: ImageIcon,
    fullscreen: isFullscreen ? Minimize2 : Expand,
  } as const

  return (
    <div className="relative flex h-full flex-col bg-white">
      <div className="absolute top-3 right-3 z-20 flex items-center gap-1 rounded-xl border border-border-subtle/80 bg-white/92 p-1.5 shadow-[0_8px_24px_rgba(15,23,42,0.08)] backdrop-blur-sm">
        {buttons.map(button => {
          const Icon = iconMap[button.id]
          const onClickMap = {
            xmind: exportXMind,
            png: exportPng,
            fullscreen: isFullscreen ? exitFullscreen : enterFullscreen,
          } as const

          return (
            <button
              key={button.id}
              onClick={onClickMap[button.id]}
              title={button.title}
              aria-label={button.label}
              className="inline-flex h-8 w-8 items-center justify-center rounded-lg text-on-surface-variant transition-all duration-200 hover:bg-surface-container hover:text-primary focus:outline-none focus:ring-2 focus:ring-primary/20"
            >
              <Icon className="h-4 w-4" />
            </button>
          )
        })}
      </div>

      {/* 如果需要编辑区，就自己加一个 <textarea> 并把 handleChange 绑上 */}
      {/* <textarea value={value} onChange={handleChange} className="mb-2 p-2 border rounded" /> */}

      {/* 思维导图区 */}
      <svg ref={svgRef} className="w-full flex-1" style={{ height, overflow: 'auto' }} />
    </div>
  )
}
