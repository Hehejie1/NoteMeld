from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Union

import networkx as nx
from networkx.algorithms import community as nx_community


class WikiGraphAnalyzer:
    COMMUNITY_COLORS = [
        "#7C5CFF",
        "#FF7C5C",
        "#33B679",
        "#2F80ED",
        "#F2994A",
        "#9B51E0",
        "#00A8A8",
        "#EB5757",
        "#27AE60",
        "#56CCF2",
        "#F2C94C",
        "#BB6BD9",
    ]

    def __init__(self, base_dir: Union[str, Path] = "wiki"):
        self.base_dir = Path(base_dir)
        self.graph_path = self.base_dir / "graph.json"
        self.cache_dir = self.base_dir / "cache"
        self.index_path = self.cache_dir / "communities_index.json"
        self._graph_cache: dict[str, dict[str, Any]] | None = None
        self._index_cache: dict[str, Any] | None = None

    def compute_and_persist_communities(self) -> dict[str, Any]:
        graph = self._read_graph()
        graph_hash = self._graph_hash(graph)

        if not graph.get("nodes"):
            index = self._empty_index(graph_hash)
            self._write_index(index)
            return {"graph_hash": graph_hash, "community_count": 0}

        graph_obj = self._to_networkx(graph)
        partition = self._partition(graph_obj)
        communities = self._build_communities(graph, graph_obj, partition)

        self._embed_communities(graph, partition, communities)
        graph["community_hash"] = graph_hash
        graph["communities"] = list(communities.values())
        self.graph_path.write_text(json.dumps(graph, ensure_ascii=False, indent=2), encoding="utf-8")

        index = {
            "computed_at": datetime.now(timezone.utc).isoformat(),
            "graph_hash": graph_hash,
            "communities": communities,
            "node_to_community": {
                node_id: {
                    "id": community_id,
                    "color": communities[str(community_id)]["color"],
                    "cohesion": communities[str(community_id)]["cohesion"],
                    "is_weak": communities[str(community_id)]["is_weak"],
                }
                for node_id, community_id in partition.items()
            },
        }
        self._write_index(index)
        self._graph_cache = {node["id"]: node for node in graph.get("nodes", [])}
        self._index_cache = index
        return {"graph_hash": graph_hash, "community_count": len(communities)}

    def read_index(self) -> dict[str, Any]:
        if self._index_cache is not None:
            return self._index_cache
        if not self.index_path.exists():
            return self._empty_index("")
        self._index_cache = json.loads(self.index_path.read_text(encoding="utf-8"))
        return self._index_cache

    def get_node_community(self, node_id: str) -> dict[str, Any] | None:
        index = self.read_index()
        community = index.get("node_to_community", {}).get(node_id)
        if community is not None:
            return community

        graph_nodes = self._read_graph_nodes()
        node = graph_nodes.get(node_id)
        if node is None or node.get("community_id") is None:
            return None
        return {
            "id": node["community_id"],
            "color": node.get("community_color"),
            "cohesion": node.get("community_cohesion"),
            "is_weak": node.get("community_is_weak", False),
        }

    def get_community(self, community_id: int | str) -> dict[str, Any] | None:
        return self.read_index().get("communities", {}).get(str(community_id))

    def get_community_members(self, community_id: int | str) -> list[str]:
        community = self.get_community(community_id)
        if community is None:
            return []
        return community.get("members", [])

    def _read_graph(self) -> dict[str, Any]:
        if not self.graph_path.exists():
            return {"nodes": [], "edges": [], "clusters": []}
        return json.loads(self.graph_path.read_text(encoding="utf-8"))

    def _read_graph_nodes(self) -> dict[str, dict[str, Any]]:
        if self._graph_cache is not None:
            return self._graph_cache
        graph = self._read_graph()
        self._graph_cache = {node["id"]: node for node in graph.get("nodes", [])}
        return self._graph_cache

    def _to_networkx(self, graph: dict[str, Any]) -> nx.Graph:
        graph_obj = nx.Graph()
        for node in graph.get("nodes", []):
            graph_obj.add_node(node["id"])
        for edge in graph.get("edges", []):
            source = edge.get("source")
            target = edge.get("target")
            if source and target:
                graph_obj.add_edge(source, target, weight=float(edge.get("weight", 1.0)))
        return graph_obj

    def _partition(self, graph_obj: nx.Graph) -> dict[str, int]:
        if graph_obj.number_of_edges() == 0:
            return {node_id: index for index, node_id in enumerate(sorted(graph_obj.nodes))}

        communities = nx_community.louvain_communities(graph_obj, weight="weight", seed=42)
        ordered = sorted([sorted(community) for community in communities], key=lambda item: item[0])
        partition: dict[str, int] = {}
        for community_id, members in enumerate(ordered):
            for node_id in members:
                partition[node_id] = community_id
        return partition

    def _build_communities(
        self,
        graph: dict[str, Any],
        graph_obj: nx.Graph,
        partition: dict[str, int],
    ) -> dict[str, dict[str, Any]]:
        members_by_community: dict[int, list[str]] = {}
        for node_id, community_id in partition.items():
            members_by_community.setdefault(community_id, []).append(node_id)

        graph_nodes = {node["id"]: node for node in graph.get("nodes", [])}
        communities: dict[str, dict[str, Any]] = {}
        for community_id, members in sorted(members_by_community.items()):
            sorted_members = sorted(members)
            cohesion = self._cohesion(graph_obj, sorted_members)
            color = self.COMMUNITY_COLORS[community_id % len(self.COMMUNITY_COLORS)]
            label = self._build_community_label(community_id, sorted_members, graph_obj, graph_nodes)
            communities[str(community_id)] = {
                "id": community_id,
                "label": label,
                "color": color,
                "size": len(sorted_members),
                "cohesion": cohesion,
                "is_weak": cohesion < 0.15,
                "members": sorted_members,
            }
        return communities

    def _embed_communities(
        self,
        graph: dict[str, Any],
        partition: dict[str, int],
        communities: dict[str, dict[str, Any]],
    ) -> None:
        for node in graph.get("nodes", []):
            community_id = partition.get(node["id"])
            if community_id is None:
                continue
            community = communities[str(community_id)]
            node["community_id"] = community_id
            node["community_color"] = community["color"]
            node["community_label"] = community["label"]
            node["community_cohesion"] = community["cohesion"]
            node["community_is_weak"] = community["is_weak"]

        community_clusters = [
            {
                "id": f"community:{community['id']}",
                "label": community["label"],
                "node_ids": community["members"],
                "type": "community",
                "color": community["color"],
                "cohesion": community["cohesion"],
                "is_weak": community["is_weak"],
            }
            for community in communities.values()
        ]
        type_clusters = [cluster for cluster in graph.get("clusters", []) if cluster.get("type", "type") != "community"]
        graph["clusters"] = type_clusters + community_clusters

    def _build_community_label(
        self,
        community_id: int,
        members: list[str],
        graph_obj: nx.Graph,
        graph_nodes: dict[str, dict[str, Any]],
    ) -> str:
        ranked_labels: list[str] = []
        seen_labels: set[str] = set()
        ranked_members = sorted(
            members,
            key=lambda node_id: (
                graph_obj.degree(node_id),
                float(graph_nodes.get(node_id, {}).get("weight", 1) or 1),
                len(self._clean_label(graph_nodes.get(node_id, {}).get("label") or node_id)),
            ),
            reverse=True,
        )

        for node_id in ranked_members:
            label = self._clean_label(graph_nodes.get(node_id, {}).get("label") or node_id)
            if not label or label in seen_labels:
                continue
            ranked_labels.append(label)
            seen_labels.add(label)
            if len(ranked_labels) >= 2:
                break

        if not ranked_labels:
            return f"社群 {community_id + 1}"
        if len(ranked_labels) == 1:
            return ranked_labels[0]
        return " / ".join(ranked_labels)

    def _clean_label(self, label: str) -> str:
        compact = " ".join(str(label).split())
        if len(compact) <= 20:
            return compact
        return f"{compact[:19]}…"

    def _cohesion(self, graph_obj: nx.Graph, members: list[str]) -> float:
        member_count = len(members)
        if member_count <= 1:
            return 1.0
        possible_edges = member_count * (member_count - 1) / 2
        internal_edges = graph_obj.subgraph(members).number_of_edges()
        return round(internal_edges / possible_edges, 3)

    def _graph_hash(self, graph: dict[str, Any]) -> str:
        nodes = sorted(
            (
                {
                    "id": node.get("id"),
                    "label": node.get("label"),
                    "type": node.get("type"),
                    "weight": node.get("weight"),
                }
                for node in graph.get("nodes", [])
            ),
            key=lambda item: item["id"],
        )
        edges = sorted(
            (
                {
                    "source": edge.get("source"),
                    "target": edge.get("target"),
                    "type": edge.get("type"),
                    "weight": edge.get("weight", 1.0),
                }
                for edge in graph.get("edges", [])
            ),
            key=lambda item: (item["source"], item["target"], item["type"]),
        )
        payload = json.dumps({"nodes": nodes, "edges": edges}, ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _empty_index(self, graph_hash: str) -> dict[str, Any]:
        return {
            "computed_at": datetime.now(timezone.utc).isoformat(),
            "graph_hash": graph_hash,
            "communities": {},
            "node_to_community": {},
        }

    def _write_index(self, index: dict[str, Any]) -> None:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
