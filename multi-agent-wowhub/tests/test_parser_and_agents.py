"""
Tests para parser y agentes del sistema multi-agente WowHub V134.2
Versión actualizada — FASE 1: async real, ModelTier, fail-loud
"""

import pytest
import json
import sys
import os
from pathlib import Path

# Fake MM_USE_MOCK antes de cualquier import
os.environ["MM_USE_MOCK"] = "true"
os.environ["MAX_ITERATIONS"] = "5"

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestCoordinatorLLM:
    """Tests para CoordinatorLLM y MockLLM."""

    def test_coordinator_singleton(self):
        from agents.base_agent import CoordinatorLLM
        c1 = CoordinatorLLM.get_instance()
        c2 = CoordinatorLLM.get_instance()
        assert c1 is c2
        assert CoordinatorLLM._instance is not None

    def test_mock_llm_response(self):
        from agents.base_agent import MockLLM, ModelTier
        mock = MockLLM(tier=ModelTier.PREMIUM)
        response = mock.complete("investig", max_tokens=100)
        assert response is not None
        result = json.loads(response)
        assert "status" in result

    def test_mock_llm_tier_fast(self):
        from agents.base_agent import MockLLM, ModelTier
        mock = MockLLM(tier=ModelTier.FAST)
        response = mock.complete("valid test", max_tokens=50)
        result = json.loads(response)
        assert result["status"] == "success"

    def test_base_agent_think(self):
        from agents.base_agent import BaseAgent, ModelTier

        class DummyAgent(BaseAgent):
            async def execute(self, task):
                return {"status": "ok"}

        agent = DummyAgent(name="test", tier=ModelTier.FAST)
        result = agent.think("test prompt", max_tokens=50)
        assert result is not None
        assert len(result) > 0


class TestOrchestrator:
    """Tests para el Orchestrator."""

    @pytest.fixture
    def orchestrator(self):
        from agents.orchestrator import Orchestrator
        return Orchestrator(session_id="test-001")

    def test_orchestrator_init(self, orchestrator):
        assert orchestrator.name == "orchestrator"
        assert orchestrator.max_iterations == 5
        assert orchestrator.session_id == "test-001"

    def test_orchestrator_state_created(self, orchestrator):
        assert orchestrator.state is not None
        assert orchestrator.state.path.exists()

    def test_classify_request_audit_before_research(self, orchestrator):
        """Bugfix: 'auditoria' debe clasificar como audit, no como research."""
        assert orchestrator._classify_request("auditoria V134.2 completa") == "audit"
        assert orchestrator._classify_request("audit de los 599 casos") == "audit"
        assert orchestrator._classify_request("directiva V134") == "audit"
        assert orchestrator._classify_request("investig") == "research"
        assert orchestrator._classify_request("codigo") == "code"
        assert orchestrator._classify_request("validar") == "validate"
        assert orchestrator._classify_request("hola mundo") == "general"

    @pytest.mark.asyncio
    async def test_execute_smoke(self, orchestrator):
        result = await orchestrator.execute_user_request("Smoke test request")
        assert result["status"] == "ok"
        assert "iterations" in result
        assert result["iterations"] >= 1

    @pytest.mark.asyncio
    async def test_research_agent_initialized(self, orchestrator):
        _ = orchestrator.researcher
        assert orchestrator._researcher is not None
        assert orchestrator._researcher.name == "researcher"

    @pytest.mark.asyncio
    async def test_coder_agent_initialized(self, orchestrator):
        _ = orchestrator.coder
        assert orchestrator._coder is not None
        assert orchestrator._coder.name == "coder"

    @pytest.mark.asyncio
    async def test_validator_agent_initialized(self, orchestrator):
        _ = orchestrator.validator
        assert orchestrator._validator is not None
        assert orchestrator._validator.name == "validator"

    def test_get_health_report(self, orchestrator):
        health = orchestrator.get_health_report()
        assert "session_id" in health
        assert "agents" in health
        assert health["agents"]["orchestrator"]["status"] == "ok"


class TestResearcher:
    """Tests para el Researcher agent."""

    @pytest.fixture
    def researcher(self):
        from agents.researcher import Researcher
        return Researcher()

    def test_researcher_init(self, researcher):
        assert researcher.name == "researcher"
        assert researcher.tier.value == "premium"

    @pytest.mark.asyncio
    async def test_execute_research(self, researcher):
        result = await researcher.execute({"task": "research", "context": {}})
        assert result["status"] == "success"


class TestCoder:
    """Tests para el Coder agent."""

    @pytest.fixture
    def coder(self):
        from agents.coder import Coder
        return Coder()

    def test_coder_init(self, coder):
        assert coder.name == "coder"
        assert coder.tier.value == "code"

    @pytest.mark.asyncio
    async def test_execute_code(self, coder):
        result = await coder.execute({"task": "implement", "context": {}})
        assert "status" in result


class TestValidator:
    """Tests para el Validator agent."""

    @pytest.fixture
    def validator(self):
        from agents.validator import Validator
        return Validator()

    def test_validator_init(self, validator):
        assert validator.name == "validator"
        assert validator.tier.value == "fast"

    @pytest.mark.asyncio
    async def test_execute_validation(self, validator):
        result = await validator.execute({"task": "valid", "context": {}})
        assert "status" in result


class TestStateManagement:
    """Tests para gestión de estado."""

    def test_state_save_load(self, tmp_path):
        from state import OrchestratorState
        state = OrchestratorState(session_id="test-state", base_path=tmp_path)
        state.set("test_key", "test_value")
        state2 = OrchestratorState(session_id="test-state", base_path=tmp_path)
        assert state2.get("test_key") == "test_value"

    def test_state_increment_iteration(self, tmp_path):
        from state import OrchestratorState
        state = OrchestratorState(session_id="test-iter", base_path=tmp_path)
        initial = state.iterations
        state.increment_iteration()
        assert state.iterations == initial + 1


class TestCPRunner:
    """Tests para el CP Runner (FASE 2)."""

    @pytest.fixture
    def runner(self):
        from runner import CPRunner
        return CPRunner(max_concurrent=5, max_retries=1)

    def test_runner_init(self, runner):
        assert runner.max_concurrent == 5
        assert runner.max_retries == 1
        assert runner.railway_url is not None

    @pytest.mark.asyncio
    async def test_run_health_endpoint(self, runner):
        """Test contra el endpoint real de Railway (mock mode)."""
        result = await runner.run_audit(
            test_cases=[{
                "id":    "CP-HEALTH-001",
                "method": "GET",
                "path":   "health",
                "expected_status": 200,
            }],
            run_id="test-health",
            resume=False,
        )
        # En mock mode, MockLLM devuelve PASS
        assert result.total_cps == 1
        # El CP puede pasar o fallar dependiendo de la red real
        # Lo importante es que no crashee


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
