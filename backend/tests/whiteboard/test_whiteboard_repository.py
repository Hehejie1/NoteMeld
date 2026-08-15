from __future__ import annotations

import math

import pytest
from pydantic import TypeAdapter, ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.engine import Base
from app.db.models.conversation import Conversation, NoteDocument  # noqa: F401
from app.models.whiteboard import (
    WhiteboardCardCreate,
    WhiteboardOperation,
    WhiteboardRelation,
)
from app.services.whiteboard_repository import (
    WhiteboardRepository,
    WhiteboardRevisionConflict,
)


def base_card_payload(card_id: str = "card_1") -> dict:
    return {
        "id": card_id,
        "type": "markdown",
        "title": "Agent loop",
        "description": "Plan, act, observe, revise",
        "content": {"markdown": "## Agent loop"},
        "source_refs": [],
        "position": {"x": 100, "y": 80},
        "size": {"width": 300, "height": 180},
        "z_index": 0,
        "collapsed": True,
    }


def create_card_op(card_id: str, **overrides) -> dict:
    card = base_card_payload(card_id) | overrides
    return {"op": "card.create", "card": card}


def create_relation_op(
    relation_id: str,
    source_card_id: str,
    target_card_id: str,
    **overrides,
) -> dict:
    relation = {
        "id": relation_id,
        "source_card_id": source_card_id,
        "target_card_id": target_card_id,
        "relation_type": "supports",
        "label": "supports",
        "description": "",
        "line_type": "bezier",
        "direction": "forward",
        "source_refs": [],
        "style": {"color": "accent", "width": "medium", "pattern": "solid"},
    }
    return {"op": "relation.create", "relation": relation | overrides}


@pytest.fixture
def repository(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'whiteboard-repository.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    repo = WhiteboardRepository(factory)
    try:
        yield repo
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    "payload",
    [
        {"type": "markdown", "content": {"markdown": ""}},
        {"type": "web", "content": {"url": "file:///etc/passwd"}},
        {"type": "file", "content": {"path": "/tmp/private.pdf"}},
        {"type": "whiteboard", "content": {"child_whiteboard_id": ""}},
    ],
)
def test_invalid_card_content_is_rejected(payload):
    with pytest.raises(ValidationError):
        WhiteboardCardCreate.model_validate(base_card_payload() | payload)


@pytest.mark.parametrize(
    ("card_type", "content"),
    [
        ("markdown", {"markdown": "# Valid"}),
        ("web", {"url": "https://example.com/research"}),
        ("file", {"upload_id": "upload_123"}),
        ("whiteboard", {"child_whiteboard_id": "wb_child"}),
    ],
)
def test_all_card_content_variants_accept_their_engine_neutral_shape(card_type, content):
    card = WhiteboardCardCreate.model_validate(
        base_card_payload() | {"type": card_type, "content": content}
    )
    assert card.content == content


def test_source_ids_preserve_existing_namespaced_repository_identity():
    card = WhiteboardCardCreate.model_validate(
        base_card_payload()
        | {
            "source_refs": [
                {
                    "source_id": "github:openai/openai-python",
                    "source_type": "github",
                    "title": "openai/openai-python",
                    "url": "https://github.com/openai/openai-python",
                }
            ]
        }
    )

    assert card.source_refs[0].source_id == "github:openai/openai-python"


@pytest.mark.parametrize(
    "patch",
    [
        {"position": {"x": math.nan, "y": 0}},
        {"position": {"x": math.inf, "y": 0}},
        {"size": {"width": 219, "height": 120}},
        {"size": {"width": 220, "height": 721}},
        {"source_refs": [
            {"source_id": f"source_{index}", "source_type": "note", "title": "Source"}
            for index in range(21)
        ]},
    ],
)
def test_card_geometry_and_sources_are_bounded(patch):
    with pytest.raises(ValidationError):
        WhiteboardCardCreate.model_validate(base_card_payload() | patch)


def test_relation_cannot_connect_card_to_itself():
    with pytest.raises(ValidationError):
        WhiteboardRelation.model_validate(
            {"id": "rel_1", "source_card_id": "card_1", "target_card_id": "card_1"}
        )


@pytest.mark.parametrize(
    "style",
    [
        {"color": "#ff0000"},
        {"width": "12px"},
        {"pattern": "url(javascript:alert(1))"},
        {"css": "position:fixed"},
    ],
)
def test_relation_style_only_accepts_enumerated_tokens(style):
    with pytest.raises(ValidationError):
        WhiteboardRelation.model_validate(
            {
                "id": "rel_1",
                "source_card_id": "card_1",
                "target_card_id": "card_2",
                "style": style,
            }
        )


@pytest.mark.parametrize(
    "operation",
    [
        {"op": "card.update", "card_id": "card_1", "patch": {"unknown": True}},
        {"op": "card.update", "card_id": "card_1", "patch": {"type": "web"}},
        {"op": "viewport.update", "x": 0, "y": 0, "zoom": 0.09},
        {"op": "viewport.update", "x": 0, "y": 0, "zoom": 2.51},
    ],
)
def test_operations_reject_unknown_patches_incomplete_type_changes_and_bad_zoom(operation):
    with pytest.raises(ValidationError):
        TypeAdapter(WhiteboardOperation).validate_python(operation)


def test_create_get_and_list_are_conversation_scoped(repository):
    first = repository.create("conv_1", "First")
    second = repository.create("conv_1", "Second", "Description")
    repository.create("conv_2", "Other conversation")

    loaded = repository.get("conv_1", first.id)
    summaries = repository.list_for_conversation("conv_1")

    assert loaded.id == first.id
    assert loaded.revision == 1
    assert loaded.viewport.model_dump() == {"x": 0.0, "y": 0.0, "zoom": 1.0}
    assert loaded.cards == []
    assert loaded.relations == []
    assert {item.id for item in summaries} == {first.id, second.id}
    with pytest.raises(LookupError):
        repository.get("conv_2", first.id)


def test_batch_create_increments_revision_once_and_snapshot_order_is_deterministic(repository):
    board = repository.create("conv_1", "Agent design")
    result = repository.apply_mutations(
        "conv_1",
        board.id,
        1,
        [
            create_card_op("card_b", z_index=2),
            create_card_op("card_c", z_index=1),
            create_card_op("card_a", z_index=1),
            create_relation_op("rel_b", "card_b", "card_c"),
            create_relation_op("rel_a", "card_a", "card_b"),
        ],
    )

    snapshot = repository.get("conv_1", board.id)
    assert result.revision == 2
    assert snapshot.revision == 2
    assert [card.id for card in snapshot.cards] == ["card_a", "card_c", "card_b"]
    assert [relation.id for relation in snapshot.relations] == ["rel_a", "rel_b"]


def test_move_resize_and_viewport_update_are_one_revision(repository):
    board = repository.create("conv_1", "Agent design")
    repository.apply_mutations("conv_1", board.id, 1, [create_card_op("card_1")])

    result = repository.apply_mutations(
        "conv_1",
        board.id,
        2,
        [
            {
                "op": "card.move_resize",
                "items": [
                    {
                        "card_id": "card_1",
                        "position": {"x": 400, "y": 240},
                        "size": {"width": 440, "height": 260},
                    }
                ],
            },
            {"op": "viewport.update", "x": -100, "y": 50, "zoom": 1.5},
        ],
    )

    snapshot = repository.get("conv_1", board.id)
    assert result.revision == 3
    assert result.viewport is not None
    assert result.viewport.model_dump() == {"x": -100.0, "y": 50.0, "zoom": 1.5}
    assert snapshot.revision == 3
    assert snapshot.cards[0].position.model_dump() == {"x": 400.0, "y": 240.0}
    assert snapshot.cards[0].size.model_dump() == {"width": 440.0, "height": 260.0}
    assert snapshot.viewport.model_dump() == {"x": -100.0, "y": 50.0, "zoom": 1.5}


def test_card_and_relation_updates_validate_and_persist(repository):
    board = repository.create("conv_1", "Agent design")
    repository.apply_mutations(
        "conv_1",
        board.id,
        1,
        [
            create_card_op("card_1"),
            create_card_op("card_2"),
            create_relation_op("rel_1", "card_1", "card_2"),
        ],
    )

    repository.apply_mutations(
        "conv_1",
        board.id,
        2,
        [
            {
                "op": "card.update",
                "card_id": "card_1",
                "patch": {"title": "Updated", "type": "web", "content": {"url": "https://example.com"}},
            },
            {
                "op": "relation.update",
                "relation_id": "rel_1",
                "patch": {
                    "relation_type": "challenges",
                    "label": "conflicts with",
                    "line_type": "smoothstep",
                    "direction": "both",
                    "style": {"color": "danger", "width": "thick", "pattern": "dashed"},
                },
            },
        ],
    )

    snapshot = repository.get("conv_1", board.id)
    assert snapshot.cards[0].title == "Updated"
    assert snapshot.cards[0].type == "web"
    assert snapshot.relations[0].relation_type == "challenges"
    assert snapshot.relations[0].style == {
        "color": "danger",
        "width": "thick",
        "pattern": "dashed",
    }


def test_card_deletion_explicitly_cascades_related_relations(repository):
    board = repository.create("conv_1", "Agent design")
    repository.apply_mutations(
        "conv_1",
        board.id,
        1,
        [
            create_card_op("card_1"),
            create_card_op("card_2"),
            create_relation_op("rel_1", "card_1", "card_2"),
        ],
    )

    result = repository.apply_mutations(
        "conv_1", board.id, 2, [{"op": "card.delete", "card_id": "card_1"}]
    )

    snapshot = repository.get("conv_1", board.id)
    assert result.deleted_card_ids == ["card_1"]
    assert result.deleted_relation_ids == ["rel_1"]
    assert [card.id for card in snapshot.cards] == ["card_2"]
    assert snapshot.relations == []


def test_relation_endpoint_must_belong_to_the_current_board(repository):
    first = repository.create("conv_1", "First")
    second = repository.create("conv_1", "Second")
    repository.apply_mutations("conv_1", first.id, 1, [create_card_op("card_1")])
    repository.apply_mutations("conv_1", second.id, 1, [create_card_op("card_2")])

    with pytest.raises(ValueError):
        repository.apply_mutations(
            "conv_1",
            first.id,
            2,
            [create_relation_op("rel_cross", "card_1", "card_2")],
        )

    assert repository.get("conv_1", first.id).revision == 2


def test_nested_whiteboard_cycle_is_rejected_without_changes(repository):
    parent = repository.create("conv_1", "Parent")
    child = repository.create("conv_1", "Child")
    repository.apply_mutations(
        "conv_1",
        parent.id,
        1,
        [
            create_card_op(
                "card_child",
                type="whiteboard",
                content={"child_whiteboard_id": child.id},
            )
        ],
    )

    with pytest.raises(ValueError, match="cycle"):
        repository.apply_mutations(
            "conv_1",
            child.id,
            1,
            [
                create_card_op(
                    "card_parent",
                    type="whiteboard",
                    content={"child_whiteboard_id": parent.id},
                )
            ],
        )

    snapshot = repository.get("conv_1", child.id)
    assert snapshot.revision == 1
    assert snapshot.cards == []


def test_nested_whiteboard_must_belong_to_same_conversation(repository):
    parent = repository.create("conv_1", "Parent")
    foreign = repository.create("conv_2", "Foreign")

    with pytest.raises(ValueError):
        repository.apply_mutations(
            "conv_1",
            parent.id,
            1,
            [
                create_card_op(
                    "card_foreign",
                    type="whiteboard",
                    content={"child_whiteboard_id": foreign.id},
                )
            ],
        )

    assert repository.get("conv_1", parent.id).cards == []


def test_mid_batch_failure_rolls_back_every_operation_and_revision(repository):
    board = repository.create("conv_1", "Agent design")

    with pytest.raises(ValueError):
        repository.apply_mutations(
            "conv_1",
            board.id,
            1,
            [create_card_op("card_1"), create_card_op("card_1")],
        )

    snapshot = repository.get("conv_1", board.id)
    assert snapshot.revision == 1
    assert snapshot.cards == []


def test_stale_revision_rolls_back_all_operations(repository):
    board = repository.create("conv_1", "Agent design")
    repository.apply_mutations("conv_1", board.id, 1, [create_card_op("card_1")])

    with pytest.raises(WhiteboardRevisionConflict) as error:
        repository.apply_mutations("conv_1", board.id, 1, [create_card_op("card_2")])

    assert error.value.current_revision == 2
    snapshot = repository.get("conv_1", board.id)
    assert snapshot.revision == 2
    assert [card.id for card in snapshot.cards] == ["card_1"]


def test_relation_delete_only_affects_current_board(repository):
    board = repository.create("conv_1", "Agent design")
    repository.apply_mutations(
        "conv_1",
        board.id,
        1,
        [
            create_card_op("card_1"),
            create_card_op("card_2"),
            create_relation_op("rel_1", "card_1", "card_2"),
        ],
    )

    result = repository.apply_mutations(
        "conv_1", board.id, 2, [{"op": "relation.delete", "relation_id": "rel_1"}]
    )

    assert result.revision == 3
    assert result.deleted_relation_ids == ["rel_1"]
    assert repository.get("conv_1", board.id).relations == []


def test_soft_deleted_board_is_hidden_from_get_and_list(repository):
    board = repository.create("conv_1", "Agent design")

    repository.soft_delete("conv_1", board.id)

    assert repository.list_for_conversation("conv_1") == []
    with pytest.raises(LookupError):
        repository.get("conv_1", board.id)
