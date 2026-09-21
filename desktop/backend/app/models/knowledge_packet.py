from dataclasses import dataclass, field
from typing import Optional


@dataclass
class KnowledgeEntity:
    name: str
    entity_type: str = "unknown"
    aliases: list[str] = field(default_factory=list)
    description: Optional[str] = None
    confidence: float = 0.0


@dataclass
class KnowledgeConcept:
    name: str
    aliases: list[str] = field(default_factory=list)
    description: str = ""
    parent: Optional[str] = None
    related: list[str] = field(default_factory=list)
    confidence: float = 0.0


@dataclass
class KnowledgeEvidence:
    evidence_id: str
    source_id: str
    source_type: str
    text: str
    timestamp: Optional[float] = None
    url: Optional[str] = None


@dataclass
class KnowledgeClaim:
    claim: str
    source: str
    target_type: str = "unknown"
    evidence_ids: list[str] = field(default_factory=list)
    confidence: float = 0.0


@dataclass
class KnowledgeRelation:
    source: str
    target: str
    relation_type: str
    weight: float = 1.0


@dataclass
class KnowledgePacket:
    packet_id: str
    source_id: str
    source_type: str
    title: str
    summary: str
    markdown_path: Optional[str] = None
    entities: list[KnowledgeEntity] = field(default_factory=list)
    concepts: list[KnowledgeConcept] = field(default_factory=list)
    claims: list[KnowledgeClaim] = field(default_factory=list)
    evidence: list[KnowledgeEvidence] = field(default_factory=list)
    relations: list[KnowledgeRelation] = field(default_factory=list)
    topics: list[str] = field(default_factory=list)


@dataclass
class GraphNode:
    id: str
    label: str
    type: str
    size: int = 8
    weight: float = 1.0
    community_id: Optional[int] = None
    community_color: Optional[str] = None
    community_label: Optional[str] = None
    community_cohesion: Optional[float] = None
    community_is_weak: bool = False


@dataclass
class GraphEdge:
    source: str
    target: str
    type: str
    weight: float = 1.0


@dataclass
class GraphCluster:
    id: str
    label: str
    node_ids: list[str] = field(default_factory=list)
    type: str = "type"
    color: Optional[str] = None
    cohesion: Optional[float] = None
    is_weak: bool = False


@dataclass
class GraphPayload:
    nodes: list[GraphNode] = field(default_factory=list)
    edges: list[GraphEdge] = field(default_factory=list)
    clusters: list[GraphCluster] = field(default_factory=list)
