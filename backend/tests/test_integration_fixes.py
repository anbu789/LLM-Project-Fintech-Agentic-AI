"""
FinTech Agent — Integration Fixes Regression Test Suite
Covers:
  1. Schedule authentication & verified principal ownership binding on /chat -> /schedules/approve
  2. Backward-compatible, safe persistence & restoration of structured turn metadata
  3. Secure CORS configuration supporting DELETE while enforcing origin allowlist
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch
import copy
import pytest
from fastapi.testclient import TestClient

from backend.app.agent.nodes.schedule_planner import schedule_planner_node
from backend.app.core.rate_limit import chat_rate_limiter
from backend.app.main import app
from backend.app.schemas.schedule import ScheduleSpec
from backend.app.services.schedule_service import schedule_service


class IsolatedCollection:
    """Thread-safe in-memory collection supporting conversation & schedule operations without touching real DBs."""

    def __init__(self):
        self.docs: List[Dict[str, Any]] = []

    def _matches(self, doc: Dict[str, Any], filt: Dict[str, Any]) -> bool:
        for key, val in (filt or {}).items():
            if doc.get(key) != val:
                return False
        return True

    def _apply_projection(self, doc: Dict[str, Any], projection: Optional[Dict[str, int]]) -> Dict[str, Any]:
        result = copy.deepcopy(doc)
        if not projection:
            return result
        include_keys = [k for k, v in projection.items() if v == 1 and k != "_id"]
        exclude_keys = [k for k, v in projection.items() if v == 0]
        if include_keys:
            projected = {k: result[k] for k in include_keys if k in result}
            if projection.get("_id") != 0 and "_id" in result:
                projected["_id"] = result["_id"]
            return projected
        for k in exclude_keys:
            result.pop(k, None)
        return result

    def insert_one(self, doc: Dict[str, Any]):
        stored = copy.deepcopy(doc)
        if "_id" not in stored:
            stored["_id"] = str(len(self.docs) + 1)
        self.docs.append(stored)
        res = MagicMock()
        res.inserted_id = stored["_id"]
        return res

    def find_one(self, query: Dict[str, Any], projection: Optional[Dict[str, int]] = None):
        for doc in self.docs:
            if self._matches(doc, query):
                return self._apply_projection(doc, projection)
        return None

    def find(self, query: Optional[Dict[str, Any]] = None, projection: Optional[Dict[str, int]] = None):
        items = [
            self._apply_projection(doc, projection)
            for doc in self.docs
            if not query or self._matches(doc, query)
        ]

        class _Cursor:
            def __init__(self, rows: List[Dict[str, Any]]):
                self._rows = rows

            def sort(self, key: str, direction: int = 1):
                self._rows.sort(key=lambda r: r.get(key, ""), reverse=(direction == -1))
                return self

            def limit(self, count: int):
                self._rows = self._rows[:count]
                return self

            def __iter__(self):
                return iter(self._rows)

        return _Cursor(items)

    def update_one(self, query: Dict[str, Any], update: Dict[str, Any], upsert: bool = False):
        target = None
        for doc in self.docs:
            if self._matches(doc, query):
                target = doc
                break

        if target is None:
            if not upsert:
                res = MagicMock()
                res.matched_count = 0
                res.modified_count = 0
                return res
            target = copy.deepcopy(query)
            target["_id"] = str(len(self.docs) + 1)
            if "$setOnInsert" in update:
                target.update(copy.deepcopy(update["$setOnInsert"]))
            self.docs.append(target)

        if "$set" in update:
            target.update(copy.deepcopy(update["$set"]))

        if "$push" in update:
            for field, push_val in update["$push"].items():
                existing_list = target.setdefault(field, [])
                if isinstance(push_val, dict) and "$each" in push_val:
                    existing_list.extend(copy.deepcopy(push_val["$each"]))
                else:
                    existing_list.append(copy.deepcopy(push_val))

        res = MagicMock()
        res.matched_count = 1
        res.modified_count = 1
        return res

    def delete_one(self, query: Dict[str, Any]):
        for idx, doc in enumerate(self.docs):
            if self._matches(doc, query):
                del self.docs[idx]
                res = MagicMock()
                res.deleted_count = 1
                return res
        res = MagicMock()
        res.deleted_count = 0
        return res


class IsolatedMetadataDB:
    def __init__(self):
        self.conversations = IsolatedCollection()
        self.schedule_previews = IsolatedCollection()
        self.scheduled_jobs = IsolatedCollection()
        self.job_runs = IsolatedCollection()
        self.scheduler_leases = IsolatedCollection()


@pytest.fixture
def isolated_db():
    db = IsolatedMetadataDB()
    chat_rate_limiter.reset()
    with patch("backend.app.api.routes.chat.mongo_manager.get_metadata_db", return_value=db), \
         patch("backend.app.services.schedule_service.mongo_manager.get_metadata_db", return_value=db):
        yield db


def _issue_token(client: TestClient, user_id: str, role: str = "analyst") -> str:
    resp = client.post("/api/v1/auth/token", json={"user_id": user_id, "role": role})
    assert resp.status_code == 200
    data = resp.json()
    assert data["token_type"] == "bearer"
    assert data["user_id"] == user_id
    return data["access_token"]


# ==============================================================================
# 1. Schedule Auth & Ownership Binding Regression Tests
# ==============================================================================

def test_authenticated_chat_binds_schedule_owner_and_allows_approval(isolated_db):
    client = TestClient(app)
    alice_token = _issue_token(client, "alice", "analyst")

    me_resp = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {alice_token}"})
    assert me_resp.status_code == 200
    assert me_resp.json()["user_id"] == "alice"

    captured_states = []

    async def fake_graph_invoke(state):
        captured_states.append(dict(state))
        node9_input = {
            **state,
            "request_mode": "SCHEDULE_ONLY",
            "intent_reason": "User requested weekly recurring report.",
            "guardrail_status": "allowed",
            "selected_collection": "customers",
            "target_collection": "customers",
            "is_pipeline_valid": True,
            "validation_status": "VALID",
            "generated_pipeline": [
                {"$group": {"_id": "$kyc_status", "count": {"$sum": 1}}},
                {"$limit": 100},
            ],
            "approved_pipeline": [
                {"$group": {"_id": "$kyc_status", "count": {"$sum": 1}}},
                {"$limit": 100},
            ],
            "pipeline_spec": [
                {"$group": {"_id": "$kyc_status", "count": {"$sum": 1}}},
                {"$limit": 100},
            ],
            "pipeline_explanation": "Groups customers by KYC verification status.",
            "temporal_spec": {
                "recurrence_expression": "Every Monday at 9 AM",
                "timezone": "Asia/Kolkata",
            },
        }
        node9_out = await schedule_planner_node(node9_input)
        return {
            **node9_input,
            **node9_out,
            "graph_response": "Schedule preview prepared for KYC status count.",
        }

    with patch("backend.app.api.routes.chat.agent_graph.ainvoke", side_effect=fake_graph_invoke):
        chat_resp = client.post(
            "/api/v1/chat",
            json={
                "message": "Generate the customer KYC-status count report every Monday at 9 AM",
                "conversation_id": "conv-sched-alice",
            },
            headers={"Authorization": f"Bearer {alice_token}"},
        )

    assert chat_resp.status_code == 200
    body = chat_resp.json()
    assert captured_states[0]["user_id"] == "alice"
    assert captured_states[0]["owner_id"] == "alice"
    assert body["schedule_preview"]["owner_id"] == "alice"
    preview_id = body["preview_id"]
    assert preview_id

    # Alice approves using her Bearer token
    approve_resp = client.post(
        "/api/v1/schedules/approve",
        json={"preview_id": preview_id, "idempotency_key": "idem-alice-1"},
        headers={"Authorization": f"Bearer {alice_token}"},
    )
    assert approve_resp.status_code == 200
    approve_data = approve_resp.json()
    assert approve_data["success"] is True
    assert approve_data["status"] == "ACTIVE"

    # Alice lists schedules and sees her newly activated job
    list_resp = client.get("/api/v1/schedules", headers={"Authorization": f"Bearer {alice_token}"})
    assert list_resp.status_code == 200
    jobs = list_resp.json()
    assert len(jobs) == 1
    assert jobs[0]["job_id"] == approve_data["job_id"]
    assert jobs[0]["owner_id"] == "alice"


def test_cross_user_cannot_approve_another_users_schedule_preview(isolated_db):
    client = TestClient(app)
    alice_token = _issue_token(client, "alice", "analyst")
    bob_token = _issue_token(client, "bob", "auditor")

    async def fake_graph_invoke(state):
        preview = schedule_service.create_preview(
            owner_id=state.get("user_id") or state.get("owner_id") or "default_user",
            report_name="Alice Weekly KYC Report",
            natural_language_query=state["natural_language_query"],
            target_collection="customers",
            pipeline_explanation="Count KYC status.",
            approved_pipeline=[
                {"$group": {"_id": "$kyc_status", "count": {"$sum": 1}}},
                {"$limit": 100},
            ],
            schedule_spec=ScheduleSpec(
                frequency="weekly",
                recurrence_expression="Every Monday at 9 AM",
                timezone="Asia/Kolkata",
                hour=9,
                minute=0,
                day_of_week=["mon"],
                cron_expression="0 9 * * 1",
                enabled=True,
            ),
            next_run_times=["2026-11-16 09:00"],
            dry_run_status="EXECUTION_GATE_BLOCKED",
        )
        return {
            **state,
            "request_mode": "SCHEDULE_ONLY",
            "selected_collection": "customers",
            "is_pipeline_valid": True,
            "pipeline_spec": preview.approved_pipeline,
            "schedule_preview": preview.model_dump(),
            "preview_id": preview.preview_id,
            "graph_response": "Schedule preview ready.",
        }

    with patch("backend.app.api.routes.chat.agent_graph.ainvoke", side_effect=fake_graph_invoke):
        chat_resp = client.post(
            "/api/v1/chat",
            json={"message": "Weekly KYC report", "conversation_id": "conv-cross-user"},
            headers={"Authorization": f"Bearer {alice_token}"},
        )

    assert chat_resp.status_code == 200
    preview_id = chat_resp.json()["preview_id"]

    # Bob tries to approve Alice's preview -> 403 Forbidden
    bob_approve = client.post(
        "/api/v1/schedules/approve",
        json={"preview_id": preview_id},
        headers={"Authorization": f"Bearer {bob_token}"},
    )
    assert bob_approve.status_code == 403

    # Anonymous user tries to approve -> 401 Unauthorized
    anon_approve = client.post("/api/v1/schedules/approve", json={"preview_id": preview_id})
    assert anon_approve.status_code == 401


def test_chat_rejects_spoofed_identity_headers_and_invalid_tokens(isolated_db):
    client = TestClient(app)
    alice_token = _issue_token(client, "alice", "analyst")

    # 1. Unsigned X-User-ID without Bearer token must be rejected
    resp_unsigned = client.post(
        "/api/v1/chat",
        json={"message": "Hello"},
        headers={"X-User-ID": "alice"},
    )
    assert resp_unsigned.status_code == 401

    # 2. Valid token with mismatched X-User-ID spoofing attempt must be rejected
    resp_spoof = client.post(
        "/api/v1/chat",
        json={"message": "Hello"},
        headers={"Authorization": f"Bearer {alice_token}", "X-User-ID": "bob"},
    )
    assert resp_spoof.status_code == 403

    # 3. Malformed Bearer token must be rejected
    resp_invalid = client.post(
        "/api/v1/chat",
        json={"message": "Hello"},
        headers={"Authorization": "Bearer not.a.valid.jwt"},
    )
    assert resp_invalid.status_code == 401


def test_unauthenticated_chat_remains_backward_compatible(isolated_db):
    client = TestClient(app)
    captured = []

    async def fake_graph_invoke(state):
        captured.append(dict(state))
        return {
            **state,
            "request_mode": "GENERAL_QA",
            "guardrail_status": "allowed",
            "graph_response": "There are 12 approved banking collections.",
        }

    with patch("backend.app.api.routes.chat.agent_graph.ainvoke", side_effect=fake_graph_invoke):
        resp = client.post("/api/v1/chat", json={"message": "What collections are available?"})

    assert resp.status_code == 200
    assert resp.json()["message"] == "There are 12 approved banking collections."
    assert "user_id" not in captured[0]


# ==============================================================================
# 2. Conversation History Structured Metadata Persistence & Backward Compatibility
# ==============================================================================

def test_conversation_persists_and_restores_structured_mql_and_schedule_preview(isolated_db):
    client = TestClient(app)
    sample_dt = datetime(2026, 11, 11, 12, 30, tzinfo=timezone.utc)
    sample_pipeline = [
        {"$match": {"status": "OPEN"}},
        {"$group": {"_id": "$account_type", "count": {"$sum": 1}}},
    ]
    sample_preview = {
        "preview_id": "prev-persist-1",
        "owner_id": "alice",
        "report_name": "Weekly Account Breakdown",
        "natural_language_query": "Weekly account breakdown",
        "target_collection": "accounts",
        "approved_pipeline": sample_pipeline,
        "schedule_spec": {"frequency": "weekly", "recurrence_expression": "Weekly", "timezone": "Asia/Kolkata"},
        "next_run_times": ["2026-11-16 09:00"],
        "dry_run_status": "SUCCESS",
        "dry_run_results": [{"_id": "SAVINGS", "count": 42, "captured_at": sample_dt}],
        "expires_at": "2026-11-11T13:00:00Z",
    }

    async def fake_graph_invoke(state):
        if "schedule" in state["natural_language_query"].lower():
            return {
                **state,
                "request_mode": "SCHEDULE_ONLY",
                "selected_collection": "accounts",
                "is_pipeline_valid": True,
                "pipeline_spec": sample_pipeline,
                "pipeline_explanation": "Aggregates open accounts by type.",
                "schedule_preview": sample_preview,
                "preview_id": "prev-persist-1",
                "graph_response": "Generated weekly schedule preview.",
            }
        return {
            **state,
            "request_mode": "QUERY",
            "selected_collection": "accounts",
            "is_pipeline_valid": True,
            "pipeline_spec": sample_pipeline,
            "pipeline_explanation": "Counts open accounts by type.",
            "graph_response": "Open account breakdown ready.",
        }

    with patch("backend.app.api.routes.chat.agent_graph.ainvoke", side_effect=fake_graph_invoke):
        r1 = client.post(
            "/api/v1/chat",
            json={"message": "Count open accounts by type", "conversation_id": "conv-structured-1"},
        )
        r2 = client.post(
            "/api/v1/chat",
            json={"message": "Schedule weekly account report", "conversation_id": "conv-structured-1"},
        )

    assert r1.status_code == 200
    assert r2.status_code == 200

    detail_resp = client.get("/api/v1/chat/conversations/conv-structured-1")
    assert detail_resp.status_code == 200
    detail = detail_resp.json()
    assert len(detail["messages"]) == 4

    # First assistant turn retains MQL metadata
    turn1_ai = detail["messages"][1]
    assert turn1_ai["role"] == "assistant"
    assert turn1_ai["pipeline_spec"] == sample_pipeline
    assert turn1_ai["selected_collection"] == "accounts"
    assert turn1_ai["validation_status"] == "passed"
    assert turn1_ai["query_explanation"] == "Counts open accounts by type."

    # Second assistant turn retains sanitized schedule_preview (datetime normalized safely to str)
    turn2_ai = detail["messages"][3]
    assert turn2_ai["preview_id"] == "prev-persist-1"
    assert turn2_ai["schedule_preview"]["preview_id"] == "prev-persist-1"
    assert isinstance(turn2_ai["schedule_preview"]["dry_run_results"][0]["captured_at"], str)


def test_legacy_conversation_records_restore_without_modification(isolated_db):
    client = TestClient(app)
    legacy_doc = {
        "conversation_id": "conv-legacy-01",
        "title": "Legacy Banking Question",
        "created_at": "2026-10-01T10:00:00Z",
        "updated_at": "2026-10-01T10:05:00Z",
        "messages": [
            {"role": "user", "content": "What is KYC?", "timestamp": "2026-10-01T10:00:00Z"},
            {"role": "assistant", "content": "Know Your Customer verification.", "timestamp": "2026-10-01T10:01:00Z"},
        ],
    }
    isolated_db.conversations.docs.append(copy.deepcopy(legacy_doc))

    detail_resp = client.get("/api/v1/chat/conversations/conv-legacy-01")
    assert detail_resp.status_code == 200
    data = detail_resp.json()
    assert len(data["messages"]) == 2
    assert data["messages"][1]["content"] == "Know Your Customer verification."
    # Verify legacy DB record itself was not mutated
    assert isolated_db.conversations.docs[0]["messages"] == legacy_doc["messages"]


# ==============================================================================
# 3. CORS Configuration Regression Tests
# ==============================================================================

def test_cors_preflight_allows_delete_and_post_for_allowed_origins_and_blocks_unknown():
    client = TestClient(app)

    # Configured frontend origin requesting DELETE must succeed
    delete_preflight = client.options(
        "/api/v1/chat/conversations/conv-123",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "DELETE",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )
    assert delete_preflight.status_code == 200
    assert delete_preflight.headers.get("access-control-allow-origin") == "http://localhost:5173"
    assert "DELETE" in delete_preflight.headers.get("access-control-allow-methods", "")
    assert delete_preflight.headers.get("access-control-allow-credentials") == "true"

    # Untrusted origin must NOT receive Access-Control-Allow-Origin
    untrusted_preflight = client.options(
        "/api/v1/chat/conversations/conv-123",
        headers={
            "Origin": "https://untrusted.example.com",
            "Access-Control-Request-Method": "DELETE",
        },
    )
    assert "access-control-allow-origin" not in untrusted_preflight.headers
