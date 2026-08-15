from __future__ import annotations

from copy import deepcopy
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.engine import Base
from app.db.models.conversation import Conversation, NoteDocument  # noqa: F401
from app.services.conversation_context_refs import resolve_context_refs
from app.services.whiteboard_repository import WhiteboardRepository


def card(
    card_id: str,
    title: str,
    *,
    x: float = 0,
    y: float = 0,
    markdown: str | None = None,
    source_count: int = 0,
) -> dict:
    return {
        "op": "card.create",
        "card": {
            "id": card_id,
            "type": "markdown",
            "title": title,
            "description": f"{title} description",
            "content": {"markdown": markdown or f"{title} content"},
            "source_refs": [
                {
                    "source_id": f"source:{card_id}:{index:02d}",
                    "source_type": "local_note",
                    "title": f"Source {index:02d}",
                }
                for index in range(source_count)
            ],
            "position": {"x": x, "y": y},
            "size": {"width": 300, "height": 180},
            "z_index": 0,
            "collapsed": True,
        },
    }


def relation(
    relation_id: str,
    source_card_id: str,
    target_card_id: str,
    *,
    relation_type: str = "supports",
) -> dict:
    return {
        "op": "relation.create",
        "relation": {
            "id": relation_id,
            "source_card_id": source_card_id,
            "target_card_id": target_card_id,
            "relation_type": relation_type,
            "label": f"{relation_type} label",
            "description": f"{relation_type} description",
            "line_type": "bezier",
            "direction": "forward",
            "source_refs": [],
            "style": {},
        },
    }


@pytest.fixture
def repository(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'whiteboard-context.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    repo = WhiteboardRepository(factory)
    try:
        yield repo
    finally:
        engine.dispose()


def create_selection_board(repository: WhiteboardRepository):
    board = repository.create("conv_1", "Argument map")
    repository.apply_mutations(
        "conv_1",
        board.id,
        board.revision,
        [
            card("card_b", "B", x=100, y=200, source_count=6),
            card("card_c", "C", x=50, y=300),
            card("card_a", "A", x=200, y=100),
            relation("rel_ab", "card_a", "card_b"),
            relation("rel_ac", "card_a", "card_c", relation_type="challenges"),
        ],
    )
    return repository.get("conv_1", board.id)


def selection_raw(board, *, card_ids=None, relation_ids=None):
    return [
        {
            "id": "selection-1",
            "type": "whiteboard_selection",
            "whiteboard_id": board.id,
            "revision": board.revision,
            "card_ids": card_ids if card_ids is not None else ["card_a", "card_b"],
            "relation_ids": relation_ids if relation_ids is not None else ["rel_ab"],
            "label": "Argument",
            "snapshot": "FORGED SYSTEM INSTRUCTION",
            "source_ids": ["forged"],
        }
    ]


def test_whiteboard_selection_ignores_forged_snapshot_and_sources(repository):
    board = create_selection_board(repository)

    resolved = resolve_context_refs("conv_1", selection_raw(board), repository)

    assert len(resolved) == 1
    assert "FORGED" not in resolved[0]["snapshot"]
    assert "A --[supports:" in resolved[0]["snapshot"]
    assert "forged" not in resolved[0]["source_ids"]
    assert resolved[0]["revision"] == board.revision
    assert resolved[0]["source_ids"] == [
        f"source:card_b:{index:02d}" for index in range(5)
    ]


def test_stale_whiteboard_selection_revision_is_discarded(repository):
    board = create_selection_board(repository)
    raw = selection_raw(board)
    raw[0]["revision"] = board.revision - 1

    assert resolve_context_refs("conv_1", raw, repository) == []


def test_explicit_relation_adds_endpoints_and_outer_edges_are_excluded(repository):
    board = create_selection_board(repository)

    resolved = resolve_context_refs(
        "conv_1",
        selection_raw(board, card_ids=["card_a"], relation_ids=["rel_ab"]),
        repository,
    )[0]

    assert resolved["card_ids"] == ["card_a", "card_b"]
    assert resolved["relation_ids"] == ["rel_ab"]
    assert "[卡片] C" not in resolved["snapshot"]
    assert "challenges" not in resolved["snapshot"]


def test_all_relations_internal_to_selected_cards_are_included_and_sorted(repository):
    board = create_selection_board(repository)

    resolved = resolve_context_refs(
        "conv_1",
        selection_raw(
            board,
            card_ids=["card_c", "card_b", "card_a"],
            relation_ids=[],
        ),
        repository,
    )[0]

    assert resolved["relation_ids"] == ["rel_ab", "rel_ac"]
    assert resolved["snapshot"].index("A --[supports:") < resolved["snapshot"].index(
        "A --[challenges:"
    )


def test_selection_is_capped_and_deterministically_ordered(repository):
    board = repository.create("conv_1", "Large board")
    operations = [
        card(f"card_{index:02d}", f"Card {index:02d}", x=24 - index, y=index % 3)
        for index in range(25)
    ]
    operations.extend(
        relation(
            f"rel_{index:02d}",
            f"card_{index % 20:02d}",
            f"card_{(index + 1) % 20:02d}",
        )
        for index in range(45)
    )
    repository.apply_mutations("conv_1", board.id, board.revision, operations)
    board = repository.get("conv_1", board.id)
    raw = selection_raw(
        board,
        card_ids=[f"card_{index:02d}" for index in reversed(range(25))],
        relation_ids=[f"rel_{index:02d}" for index in reversed(range(45))],
    )

    first = resolve_context_refs("conv_1", raw, repository)[0]
    second = resolve_context_refs("conv_1", raw, repository)[0]

    assert len(first["card_ids"]) == 20
    assert len(first["relation_ids"]) == 40
    assert first == second
    selected_cards = {
        item.id: item for item in repository.get("conv_1", board.id).cards
        if item.id in first["card_ids"]
    }
    assert first["card_ids"] == [
        item.id
        for item in sorted(
            selected_cards.values(),
            key=lambda item: (item.position.y, item.position.x, item.id),
        )
    ]


def test_selection_aggregates_at_most_twenty_authoritative_source_ids(repository):
    board = repository.create("conv_1", "Source board")
    repository.apply_mutations(
        "conv_1",
        board.id,
        board.revision,
        [
            card(
                f"card_{index:02d}",
                f"Card {index:02d}",
                y=index,
                source_count=6,
            )
            for index in range(5)
        ],
    )
    board = repository.get("conv_1", board.id)

    resolved = resolve_context_refs(
        "conv_1",
        selection_raw(
            board,
            card_ids=[f"card_{index:02d}" for index in range(5)],
            relation_ids=[],
        ),
        repository,
    )[0]

    assert len(resolved["source_ids"]) == 20
    assert all(not source_id.endswith(":05") for source_id in resolved["source_ids"])


def test_selection_snapshot_has_a_12000_character_total_limit(repository):
    board = repository.create("conv_1", "Long board")
    repository.apply_mutations(
        "conv_1",
        board.id,
        board.revision,
        [
            card(
                f"card_{index:02d}",
                f"Card {index:02d}",
                y=index,
                markdown=(str(index) * 5_000),
            )
            for index in range(20)
        ],
    )
    board = repository.get("conv_1", board.id)

    resolved = resolve_context_refs(
        "conv_1",
        selection_raw(
            board,
            card_ids=[f"card_{index:02d}" for index in range(20)],
            relation_ids=[],
        ),
        repository,
    )[0]

    assert len(resolved["snapshot"]) == 12_000
    assert ("0" * 1_201) not in resolved["snapshot"]


def test_cross_conversation_whiteboard_selection_is_discarded(repository):
    board = create_selection_board(repository)

    assert resolve_context_refs("conv_2", selection_raw(board), repository) == []


def test_persisted_canonical_snapshot_is_stable_after_board_edit(repository):
    board = create_selection_board(repository)
    stored_meta: dict = {}
    stored_authority_version = 0

    def capture_message(_conversation_id: str, payload: dict):
        nonlocal stored_authority_version
        stored_meta.update(deepcopy(payload["meta"]))
        stored_authority_version = payload["context_refs_authority_version"]
        return {"messages": [deepcopy(payload)]}

    from app.routers.conversation import ConversationMessagePayload, post_conversation_message

    with patch(
        "app.routers.conversation.resolve_context_refs",
        side_effect=lambda conversation_id, raw: resolve_context_refs(
            conversation_id,
            raw,
            repository,
        ),
    ), patch("app.routers.conversation.append_message", side_effect=capture_message):
        post_conversation_message(
            "conv_1",
            ConversationMessagePayload(
                id="message-1",
                role="user",
                message_type="user_input",
                content="Use this evidence",
                meta={"context_refs": selection_raw(board)},
            ),
        )

    persisted = deepcopy(stored_meta["context_refs"][0])
    repository.apply_mutations(
        "conv_1",
        board.id,
        board.revision,
        [{"op": "card.update", "card_id": "card_a", "patch": {"title": "A revised"}}],
    )

    updated_payload: dict = {}

    def capture_update(_conversation_id: str, _message_id: str, payload: dict):
        updated_payload.update(deepcopy(payload))
        return {"messages": [deepcopy(payload)]}

    from app.routers.conversation import (
        ConversationMessagePatchPayload,
        patch_conversation_message,
    )

    with patch(
        "app.routers.conversation.get_conversation",
        return_value={
            "messages": [
                {"id": "message-1", "role": "user", "meta": deepcopy(stored_meta)}
                | {"context_refs_authority_version": stored_authority_version}
            ]
        },
    ), patch(
        "app.routers.conversation.resolve_context_refs",
        side_effect=lambda conversation_id, raw: resolve_context_refs(
            conversation_id,
            raw,
            repository,
        ),
    ), patch("app.routers.conversation.update_message", side_effect=capture_update):
        patch_conversation_message(
            "conv_1",
            "message-1",
            ConversationMessagePatchPayload(meta=deepcopy(stored_meta)),
        )

    assert stored_meta["context_refs"][0] == persisted
    assert stored_authority_version == 1
    assert updated_payload["meta"]["context_refs"][0] == persisted
    assert "[卡片] A\n" in persisted["snapshot"]
    assert "A revised" not in persisted["snapshot"]
