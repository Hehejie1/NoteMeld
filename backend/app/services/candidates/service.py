from __future__ import annotations

import json
import uuid
from typing import Any

from app.db.engine import SessionLocal
from app.db.models.candidate import Candidate, CandidateArtifact, CandidateDecision, CandidateEvaluation, CandidateEvidence
from app.db.models.plugin import PluginInstallation


ALLOWED_KINDS = {"application", "plugin"}
ALLOWED_PERMISSIONS = {"application.read", "application.test", "application.patch.review", "plugin.package"}
SDK_DENY_MARKERS = (
    "notemeld-agent-sdk",
    "notemeld_agent",
    "notemeld-agent",
    "agent-sdk",
    "agent_sdk",
    "sdk_path",
    "sdk_artifact",
    "sdk_source",
    "/crates/agent-",
    "crates/agent-",
    "/bindings/",
    "bindings/",
    "/include/notemeld_agent",
    "include/notemeld_agent",
    "/schemas/",
    "abi-v",
    "abi_path",
    "binding_path",
    "schema_path",
    "public-contract",
    "public_contract",
    "public contract",
)
APP_SCOPE_PREFIXES = ("backend/", "frontend/", "desktop/", "packaging/", "docs/")


class CandidateValidationError(ValueError):
    pass


class CandidateNotFound(LookupError):
    pass


class CandidateNotApprovable(ValueError):
    pass


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _loads(value: str, default: Any) -> Any:
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return default


def _contains_denied_marker(value: Any) -> str | None:
    haystack = _json(value).lower()
    return next((marker for marker in SDK_DENY_MARKERS if marker in haystack), None)


def _non_empty(value: Any) -> bool:
    return bool(value) and value != {} and value != [] and value != ""


class CandidateService:
    def __init__(self, session_factory=None):
        self.session_factory = session_factory or SessionLocal

    def create(self, payload: dict[str, Any]) -> dict[str, Any]:
        kind = payload.get("kind")
        if kind not in ALLOWED_KINDS:
            raise CandidateValidationError("candidate kind must be application or plugin")
        if not str(payload.get("title", "")).strip():
            raise CandidateValidationError("candidate title is required")
        candidate = Candidate(
            id=uuid.uuid4().hex,
            kind=kind,
            title=str(payload["title"]).strip(),
            scope_json=_json(payload.get("scope", {})),
            evidence_json=_json(payload.get("evidence", [])),
            trace_json=_json(payload.get("trace", [])),
            artifact_json=_json(payload.get("artifact", {})),
            patch_json=_json(payload.get("patch", {})),
            tests_json=_json(payload.get("tests", [])),
            risks_json=_json(payload.get("risks", [])),
            permissions_json=_json(payload.get("permissions", [])),
            rollback_json=_json(payload.get("rollback", {})),
            model_safety_claim=payload.get("model_safety_claim"),
        )
        with self.session_factory.begin() as db:
            db.add(candidate)
            for kind, entries in (("evidence", payload.get("evidence", [])), ("trace", payload.get("trace", []))):
                for entry in entries if isinstance(entries, list) else []:
                    db.add(CandidateEvidence(id=uuid.uuid4().hex, candidate_id=candidate.id, kind=kind, payload_json=_json(entry)))
            for kind, entry in (("artifact", payload.get("artifact", {})), ("patch", payload.get("patch", {}))):
                db.add(CandidateArtifact(id=uuid.uuid4().hex, candidate_id=candidate.id, kind=kind, payload_json=_json(entry)))
            for entry in payload.get("tests", []) if isinstance(payload.get("tests", []), list) else []:
                db.add(CandidateEvaluation(id=uuid.uuid4().hex, candidate_id=candidate.id, status=entry.get("status", "unknown") if isinstance(entry, dict) else "unknown", payload_json=_json(entry)))
            return self.serialize(candidate)

    def list(self) -> list[dict[str, Any]]:
        with self.session_factory() as db:
            rows = db.query(Candidate).order_by(Candidate.created_at.desc(), Candidate.id.desc()).all()
            return [self.serialize(row) for row in rows]

    def get(self, candidate_id: str) -> dict[str, Any]:
        with self.session_factory() as db:
            candidate = db.get(Candidate, candidate_id)
            if candidate is None:
                raise CandidateNotFound(candidate_id)
            return self.serialize(candidate)

    def validate(self, candidate_id: str) -> dict[str, Any]:
        with self.session_factory.begin() as db:
            candidate = db.get(Candidate, candidate_id)
            if candidate is None:
                raise CandidateNotFound(candidate_id)
            candidate.status = "validating"
            errors = self._validation_errors(candidate, db)
            candidate.validation_json = _json({"errors": errors, "model_safety_claim_used": False})
            candidate.status = "approvable" if not errors else "rejected"
            return self.serialize(candidate, errors=errors)

    def decide(self, candidate_id: str, *, approved: bool, actor: str, reason: str | None = None) -> dict[str, Any]:
        with self.session_factory.begin() as db:
            candidate = db.get(Candidate, candidate_id)
            if candidate is None:
                raise CandidateNotFound(candidate_id)
            if approved:
                errors = self._validation_errors(candidate, db)
                if errors:
                    raise CandidateNotApprovable("candidate is not approvable: " + "; ".join(errors))
                candidate.status = "approved"
            else:
                candidate.status = "declined"
            candidate.decision_actor = actor or "user"
            candidate.decision_reason = reason
            db.add(CandidateDecision(
                id=uuid.uuid4().hex,
                candidate_id=candidate.id,
                decision="approved" if approved else "declined",
                actor=actor or "user",
                reason=reason,
            ))
            return self.serialize(candidate)

    def _validation_errors(self, candidate: Candidate, db=None) -> list[str]:
        scope = _loads(candidate.scope_json, {})
        evidence = _loads(candidate.evidence_json, [])
        trace = _loads(candidate.trace_json, [])
        artifact = _loads(candidate.artifact_json, {})
        patch = _loads(candidate.patch_json, {})
        tests = _loads(candidate.tests_json, [])
        risks = _loads(candidate.risks_json, [])
        permissions = _loads(candidate.permissions_json, [])
        rollback = _loads(candidate.rollback_json, {})
        errors: list[str] = []
        if candidate.kind not in ALLOWED_KINDS:
            errors.append("unsupported candidate kind")
        if scope.get("kind") != candidate.kind:
            errors.append("scope kind must match candidate kind")
        targets = scope.get("targets")
        if not isinstance(targets, list) or not targets:
            errors.append("scope targets are required")
        else:
            for target in targets:
                if not isinstance(target, str) or target.startswith("/") or ".." in target:
                    errors.append("scope contains an unsafe path")
                elif candidate.kind == "application" and not target.startswith(APP_SCOPE_PREFIXES):
                    errors.append("application scope is outside the allowlist")
                elif candidate.kind == "plugin":
                    plugin_id = target.removeprefix("plugin:")
                    if not target.startswith("plugin:") or not plugin_id or db is None or db.get(PluginInstallation, plugin_id) is None:
                        errors.append("plugin scope must target an installed plugin")
        if not _non_empty(evidence):
            errors.append("evidence is required")
        if not _non_empty(trace):
            errors.append("trace is required")
        if not _non_empty(artifact):
            errors.append("artifact metadata is required")
        if not _non_empty(patch):
            errors.append("patch metadata is required")
        if not _non_empty(tests):
            errors.append("tests are required")
        elif any(not isinstance(item, dict) or item.get("status") != "passed" for item in tests):
            errors.append("all tests must have passed status")
        if not _non_empty(risks):
            errors.append("risk assessment is required")
        if not _non_empty(rollback):
            errors.append("rollback plan is required")
        if not isinstance(permissions, list) or any(item not in ALLOWED_PERMISSIONS for item in permissions):
            errors.append("requested permissions exceed candidate authority")
        boundary = {"scope": scope, "evidence": evidence, "trace": trace, "artifact": artifact, "patch": patch, "tests": tests, "risks": risks, "permissions": permissions, "rollback": rollback}
        marker = _contains_denied_marker(boundary)
        if marker:
            errors.append(f"SDK/public contract boundary denied: {marker}")
        return list(dict.fromkeys(errors))

    @staticmethod
    def serialize(candidate: Candidate, *, errors: list[str] | None = None) -> dict[str, Any]:
        result = {
            "id": candidate.id,
            "kind": candidate.kind,
            "title": candidate.title,
            "status": candidate.status,
            "scope": _loads(candidate.scope_json, {}),
            "evidence": _loads(candidate.evidence_json, []),
            "trace": _loads(candidate.trace_json, []),
            "artifact": _loads(candidate.artifact_json, {}),
            "patch": _loads(candidate.patch_json, {}),
            "tests": _loads(candidate.tests_json, []),
            "risks": _loads(candidate.risks_json, []),
            "permissions": _loads(candidate.permissions_json, []),
            "rollback": _loads(candidate.rollback_json, {}),
            "model_safety_claim": candidate.model_safety_claim,
            "validation": _loads(candidate.validation_json, {}),
            "decision_actor": candidate.decision_actor,
            "decision_reason": candidate.decision_reason,
        }
        if errors is not None:
            result["validation"] = {"errors": errors, "model_safety_claim_used": False}
        if candidate.kind == "plugin":
            result["next_step"] = "convert to an N03 standard package and repeat verifier/permission/active-pointer flow"
        else:
            result["next_step"] = "manual review only; no application patch or activation in N06"
        return result
