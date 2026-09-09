import React, { useEffect, useState } from 'react';
import { Button } from '@/components/ui/button.tsx';
import request from '@/utils/request';
import toast from 'react-hot-toast';
import { RefreshCw } from 'lucide-react';
import KnowledgeEmptyState from '@/components/KnowledgeEmptyState';
import {
  cancelWikiExtraction,
  getWikiArticleDetail,
  type WikiArticleClaim,
  type WikiArticleConcept,
  type WikiArticleDetail,
  type WikiArticleEntity,
  type WikiArticleEvidence,
  type WikiArticleRelation,
} from '@/services/wiki';

interface WikiViewerProps {
  taskId: string;
  wikiStatus: 'pending' | 'success' | 'failed' | string;
  onRetrySuccess?: () => void;
}

interface WikiJobStatus {
  status?: string;
  reason?: string;
  detail?: string;
  recoverable?: boolean;
}

const formatConfidence = (value?: number) => {
  if (typeof value !== 'number' || Number.isNaN(value)) return '';
  return `${Math.round(value * 100)}%`;
};

const WikiViewer: React.FC<WikiViewerProps> = ({ taskId, wikiStatus, onRetrySuccess }) => {
  const [loading, setLoading] = useState(true);
  const [article, setArticle] = useState<WikiArticleDetail | null>(null);
  const [error, setError] = useState(false);
  const [retrying, setRetrying] = useState(false);
  const [canceling, setCanceling] = useState(false);
  const [localWikiStatus, setLocalWikiStatus] = useState(wikiStatus || 'pending');
  const [jobStatus, setJobStatus] = useState<WikiJobStatus | null>(null);

  useEffect(() => {
    setLocalWikiStatus(wikiStatus || 'pending');
  }, [wikiStatus, taskId]);

  useEffect(() => {
    if (!taskId) return;
    request.get(`/wiki/status/${taskId}`)
      .then(res => setJobStatus(res as unknown as WikiJobStatus))
      .catch(() => setJobStatus(null));
  }, [taskId, localWikiStatus]);

  useEffect(() => {
    if (!taskId) {
      setLoading(false);
      setError(false);
      setArticle(null);
      return;
    }

    setLoading(true);
    setError(false);
    getWikiArticleDetail(taskId)
      .then(detail => {
        setArticle(detail);
        setError(false);
      })
      .catch(() => {
        setArticle(null);
        setError(localWikiStatus === 'failed' || ['success', 'partial'].includes(localWikiStatus));
      })
      .finally(() => {
        setLoading(false);
      });
  }, [taskId, localWikiStatus]);

  const handleRetry = async () => {
    setRetrying(true);
    try {
      await request.post(`/wiki/retry/${taskId}`);
      setLocalWikiStatus('pending');
      toast.success('已触发重试，请稍候');
      
      let attempts = 0;
      const timer = setInterval(async () => {
        attempts++;
        try {
          const res = (await request.get(`/wiki/status/${taskId}`)) as unknown as WikiJobStatus;
          setJobStatus(res);
          if (res?.status === 'success' || res?.status === 'partial') {
            setError(false);
            setLocalWikiStatus(res.status);
            clearInterval(timer);
            setRetrying(false);
            toast.success(res.status === 'partial' ? '已生成基础 Wiki，可稍后继续增强' : 'Wiki 提取成功！');
            onRetrySuccess?.();
          } else if (res?.status === 'failed') {
            clearInterval(timer);
            setRetrying(false);
            setLocalWikiStatus('failed');
            toast.error('Wiki 提取失败');
          }
        } catch {
          if (attempts > 15) {
            clearInterval(timer);
            setRetrying(false);
            toast.error('重试超时');
          }
        }
      }, 3000);
    } catch {
      toast.error('触发重试失败');
      setRetrying(false);
    }
  };

  const handleCancel = async () => {
    if (!taskId) return;
    setCanceling(true);
    try {
      const res = await cancelWikiExtraction(taskId);
      setJobStatus(res as WikiJobStatus);
      setLocalWikiStatus('canceled');
      toast.success('已取消 Wiki 提取');
      onRetrySuccess?.();
    } catch {
      toast.error('取消提取失败');
    } finally {
      setCanceling(false);
    }
  };

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center bg-white px-6">
        <KnowledgeEmptyState
          status="loading"
          title="正在读取文章 Wiki"
          description="正在加载当前文章抽取出的实体、概念、观点和证据。"
        />
      </div>
    );
  }

  if (!taskId) {
    return (
      <div className="flex h-full items-center justify-center bg-white px-6">
        <KnowledgeEmptyState
          title="选择一篇笔记，查看它沉淀出的 Wiki"
          description="这里展示选中文章自己的实体、概念、观点、证据和关系。"
        />
      </div>
    );
  }

  if (localWikiStatus === 'pending' && !article) {
    return (
      <div className="flex h-full items-center justify-center bg-white px-6">
        <KnowledgeEmptyState
          status="loading"
          title="Wiki 正在提取中"
          description="正在从正文中识别关键实体、核心概念和可追溯证据，完成后会自动出现在这里。"
          action={
            <Button onClick={handleCancel} disabled={canceling} variant="outline">
              {canceling ? '正在取消...' : '取消提取'}
            </Button>
          }
        />
      </div>
    );
  }

  if (localWikiStatus === 'canceled' && !article) {
    return (
      <div className="flex h-full items-center justify-center bg-white px-6">
        <KnowledgeEmptyState
          status="empty"
          title="Wiki 提取已取消"
          description="你已取消当前笔记的 Wiki 提取，可以稍后重新触发。"
          detail={jobStatus?.detail}
          action={
            <Button onClick={handleRetry} disabled={retrying} variant="outline">
              <RefreshCw className={`mr-2 h-4 w-4 ${retrying ? 'animate-spin' : ''}`} />
              {retrying ? '正在重试...' : '重新提取'}
            </Button>
          }
        />
      </div>
    );
  }

  if (error || !article) {
    return (
      <div className="flex h-full items-center justify-center bg-white px-6">
        <KnowledgeEmptyState
          status="error"
          title="Wiki 还没有成功生成"
          description="当前笔记的知识页暂时不可用，可以重新触发提取。"
          detail={jobStatus?.detail}
          action={
            <Button onClick={handleRetry} disabled={retrying} variant="outline">
              <RefreshCw className={`mr-2 h-4 w-4 ${retrying ? 'animate-spin' : ''}`} />
              {retrying ? '正在重试...' : '重试提取'}
            </Button>
          }
        />
      </div>
    );
  }

  const renderEntity = (entity: WikiArticleEntity) => (
    <article key={entity.name} className="rounded-2xl border border-neutral-100 bg-white p-4 shadow-sm">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="text-base font-semibold text-neutral-900">{entity.name}</h3>
          <div className="mt-1 flex flex-wrap gap-2 text-xs text-neutral-500">
            {entity.entity_type && <span className="rounded-full bg-neutral-100 px-2 py-0.5">{entity.entity_type}</span>}
            {formatConfidence(entity.confidence) && <span className="rounded-full bg-emerald-50 px-2 py-0.5 text-emerald-700">置信度 {formatConfidence(entity.confidence)}</span>}
          </div>
        </div>
      </div>
      {entity.description && <p className="mt-3 text-sm leading-6 text-neutral-700">{entity.description}</p>}
      {entity.aliases && entity.aliases.length > 0 && (
        <div className="mt-3 text-xs text-neutral-500">别名：{entity.aliases.join('、')}</div>
      )}
      {entity.claims && entity.claims.length > 0 && (
        <ul className="mt-3 space-y-1 text-sm text-neutral-700">
          {entity.claims.map(claim => <li key={claim}>- {claim}</li>)}
        </ul>
      )}
    </article>
  );

  const renderConcept = (concept: WikiArticleConcept) => (
    <article key={concept.name} className="rounded-2xl border border-violet-100 bg-violet-50/40 p-4">
      <div className="flex items-start justify-between gap-3">
        <h3 className="text-base font-semibold text-neutral-900">{concept.name}</h3>
        {formatConfidence(concept.confidence) && <span className="rounded-full bg-white px-2 py-0.5 text-xs text-violet-700">置信度 {formatConfidence(concept.confidence)}</span>}
      </div>
      {concept.description && <p className="mt-3 text-sm leading-6 text-neutral-700">{concept.description}</p>}
      {concept.related && concept.related.length > 0 && (
        <div className="mt-3 text-xs text-neutral-500">相关：{concept.related.join('、')}</div>
      )}
      {concept.claims && concept.claims.length > 0 && (
        <ul className="mt-3 space-y-1 text-sm text-neutral-700">
          {concept.claims.map(claim => <li key={claim}>- {claim}</li>)}
        </ul>
      )}
    </article>
  );

  const renderClaim = (claim: WikiArticleClaim) => (
    <li key={`${claim.target_name || ''}:${claim.claim}`} className="rounded-xl border border-neutral-100 bg-white px-3 py-2 text-sm text-neutral-700">
      <span>{claim.claim}</span>
      {claim.target_name && <span className="ml-2 text-xs text-neutral-400">#{claim.target_name}</span>}
    </li>
  );

  const renderEvidence = (item: WikiArticleEvidence) => (
    <li key={item.evidence_id} className="rounded-xl border border-neutral-100 bg-white px-3 py-2 text-sm leading-6 text-neutral-700">
      {item.text}
    </li>
  );

  const renderRelation = (relation: WikiArticleRelation) => (
    <li key={`${relation.source}:${relation.relation_type}:${relation.target}`} className="rounded-xl border border-neutral-100 bg-white px-3 py-2 text-sm text-neutral-700">
      <span className="font-medium text-neutral-900">{relation.source}</span>
      <span className="mx-2 text-neutral-400">{relation.relation_type}</span>
      <span className="font-medium text-neutral-900">{relation.target}</span>
    </li>
  );

  return (
    <div className="h-full overflow-auto bg-white">
      <main className="mx-auto max-w-5xl p-6">
        <div className="mb-5 rounded-3xl border border-neutral-100 bg-neutral-50/70 p-5">
          <div className="text-xs font-medium tracking-[0.14em] text-neutral-400">ARTICLE WIKI</div>
          <h2 className="mt-2 text-2xl font-semibold text-neutral-950">{article.title}</h2>
          {article.summary && <p className="mt-3 text-sm leading-7 text-neutral-700">{article.summary}</p>}
          <div className="mt-4 flex flex-wrap gap-2 text-xs">
            <span className="rounded-full bg-white px-3 py-1 text-neutral-600">实体 {article.entities.length}</span>
            <span className="rounded-full bg-white px-3 py-1 text-neutral-600">概念 {article.concepts.length}</span>
            <span className="rounded-full bg-white px-3 py-1 text-neutral-600">观点 {article.claims.length}</span>
            <span className="rounded-full bg-white px-3 py-1 text-neutral-600">证据 {article.evidence.length}</span>
            <span className="rounded-full bg-white px-3 py-1 text-neutral-600">关系 {article.relations.length}</span>
          </div>
        </div>

        {localWikiStatus === 'partial' && (
          <div className="mb-4 rounded-2xl border border-amber-100 bg-amber-50/80 px-4 py-3 text-sm text-amber-800">
            已生成基础 Wiki。结构化实体与概念抽取未完全成功，可点击重试继续增强。
            {jobStatus?.detail && <span className="ml-2 text-amber-700/80">原因：{jobStatus.detail}</span>}
            <Button onClick={handleRetry} disabled={retrying} variant="outline" size="sm" className="ml-3 border-amber-200 bg-white/70">
              <RefreshCw className={`mr-2 h-3.5 w-3.5 ${retrying ? 'animate-spin' : ''}`} />
              {retrying ? '正在重试' : '重试增强'}
            </Button>
          </div>
        )}

        <section className="mb-6">
          <div className="mb-3 flex items-center justify-between">
            <h3 className="text-sm font-semibold text-neutral-900">本篇实体</h3>
            <span className="text-xs text-neutral-400">{article.entities.length} 个</span>
          </div>
          <div className="grid gap-3 md:grid-cols-2">
            {article.entities.map(renderEntity)}
            {article.entities.length === 0 && <div className="rounded-2xl border border-dashed border-neutral-200 p-4 text-sm text-neutral-400">这篇文章未抽取到实体。</div>}
          </div>
        </section>

        <section className="mb-6">
          <div className="mb-3 flex items-center justify-between">
            <h3 className="text-sm font-semibold text-neutral-900">本篇概念</h3>
            <span className="text-xs text-neutral-400">{article.concepts.length} 个</span>
          </div>
          <div className="grid gap-3 md:grid-cols-2">
            {article.concepts.map(renderConcept)}
            {article.concepts.length === 0 && <div className="rounded-2xl border border-dashed border-neutral-200 p-4 text-sm text-neutral-400">这篇文章未抽取到概念。</div>}
          </div>
        </section>

        <section className="mb-6 grid gap-4 lg:grid-cols-2">
          <div>
            <div className="mb-3 flex items-center justify-between">
              <h3 className="text-sm font-semibold text-neutral-900">本篇观点</h3>
              <span className="text-xs text-neutral-400">{article.claims.length} 条</span>
            </div>
            <ul className="space-y-2">
              {article.claims.map(renderClaim)}
              {article.claims.length === 0 && <li className="rounded-2xl border border-dashed border-neutral-200 p-4 text-sm text-neutral-400">暂无观点。</li>}
            </ul>
          </div>
          <div>
            <div className="mb-3 flex items-center justify-between">
              <h3 className="text-sm font-semibold text-neutral-900">本篇证据</h3>
              <span className="text-xs text-neutral-400">{article.evidence.length} 条</span>
            </div>
            <ul className="space-y-2">
              {article.evidence.map(renderEvidence)}
              {article.evidence.length === 0 && <li className="rounded-2xl border border-dashed border-neutral-200 p-4 text-sm text-neutral-400">暂无证据。</li>}
            </ul>
          </div>
        </section>

        <section>
          <div className="mb-3 flex items-center justify-between">
            <h3 className="text-sm font-semibold text-neutral-900">本篇关系</h3>
            <span className="text-xs text-neutral-400">{article.relations.length} 条</span>
          </div>
          <ul className="space-y-2">
            {article.relations.map(renderRelation)}
            {article.relations.length === 0 && <li className="rounded-2xl border border-dashed border-neutral-200 p-4 text-sm text-neutral-400">暂无关系。</li>}
          </ul>
        </section>
      </main>
    </div>
  );
};

export default WikiViewer;
