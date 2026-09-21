from dataclasses import dataclass, field
from typing import Optional


@dataclass
class WikiAnalysisEntity:
    name: str
    normalized_name: str
    entity_type: str = "unknown"
    aliases: list[str] = field(default_factory=list)
    description: str = ""
    confidence: float = 0.0


@dataclass
class WikiAnalysisConcept:
    name: str
    normalized_name: str
    aliases: list[str] = field(default_factory=list)
    description: str = ""
    parent: Optional[str] = None
    related: list[str] = field(default_factory=list)
    confidence: float = 0.0


@dataclass
class WikiAnalysisEvidence:
    evidence_id: str
    text: str
    source_id: str
    source_type: str
    timestamp: Optional[float] = None
    url: Optional[str] = None


@dataclass
class WikiAnalysisClaim:
    claim: str
    target_type: str
    target_name: str
    evidence_ids: list[str] = field(default_factory=list)
    confidence: float = 0.0


@dataclass
class WikiAnalysisRelation:
    source: str
    target: str
    relation_type: str
    weight: float = 1.0


@dataclass
class WikiAnalysis:
    source_id: str
    source_type: str
    title: str
    summary: str
    entities: list[WikiAnalysisEntity] = field(default_factory=list)
    concepts: list[WikiAnalysisConcept] = field(default_factory=list)
    claims: list[WikiAnalysisClaim] = field(default_factory=list)
    evidence: list[WikiAnalysisEvidence] = field(default_factory=list)
    relations: list[WikiAnalysisRelation] = field(default_factory=list)
    topics: list[str] = field(default_factory=list)
