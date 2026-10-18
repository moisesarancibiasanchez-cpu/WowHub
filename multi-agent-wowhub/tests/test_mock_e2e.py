"""
End-to-end tests con MockLLM para WowHub Multi-Agent System V134.2
"""

import pytest
import asyncio
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

os.environ["MM_USE_MOCK"] = "true"
os.environ["MAX_ITERATIONS"] = "5"


@pytest.mark.asyncio
async def test_full_flow_research():
    """Test flujo completo: Orchestrator -> Researcher."""
    from agents.orchestrator import Orchestrator
    
    orch = Orchestrator(session_id="e2e-research")
    result = await orch.execute_user_request("investig")
    
    assert result["status"] == "ok"
    assert result["task_type"] == "research"
    assert "result" in result


@pytest.mark.asyncio
async def test_full_flow_code():
    """Test flujo completo: Orchestrator -> Researcher -> Coder."""
    from agents.orchestrator import Orchestrator
    
    orch = Orchestrator(session_id="e2e-code")
    result = await orch.execute_user_request("implement")
    
    assert result["status"] == "ok"
    assert result["task_type"] == "code"
    assert "result" in result


@pytest.mark.asyncio
async def test_full_flow_validate():
    """Test flujo completo: Orchestrator -> Validator."""
    from agents.orchestrator import Orchestrator
    
    orch = Orchestrator(session_id="e2e-validate")
    result = await orch.execute_user_request("valid")
    
    assert result["status"] == "ok"
    assert result["task_type"] == "validate"
    assert "result" in result


@pytest.mark.asyncio
async def test_orchestrator_iteration_count():
    """Test que las iteraciones se incrementan correctamente."""
    from agents.orchestrator import Orchestrator
    
    orch = Orchestrator(session_id="e2e-iter")
    
    initial = orch.state.iterations
    
    await orch.execute_user_request("test")
    await orch.execute_user_request("test")
    await orch.execute_user_request("test")
    
    assert orch.state.iterations == initial + 3


@pytest.mark.asyncio
async def test_all_agents_healthy():
    """Test que todos los agentes estan saludables."""
    from agents.orchestrator import Orchestrator
    
    orch = Orchestrator(session_id="e2e-health")
    
    _ = orch.researcher
    _ = orch.coder
    _ = orch.validator
    
    health = orch.get_health_report()
    
    assert health["agents"]["orchestrator"]["status"] == "ok"
    assert health["agents"]["researcher"]["status"] == "ok"
    assert health["agents"]["coder"]["status"] == "ok"
    assert health["agents"]["validator"]["status"] == "ok"


@pytest.mark.asyncio
async def test_state_persists_across_agents():
    """Test que el estado persiste entre ejecuciones."""
    from agents.orchestrator import Orchestrator
    
    session_id = "e2e-persist"
    orch = Orchestrator(session_id=session_id)
    
    await orch.execute_user_request("investig")
    await orch.execute_user_request("codig")
    
    assert orch.state.iterations >= 2
    assert orch.state.get("last_task") is not None


@pytest.mark.asyncio
async def test_concurrent_requests():
    """Test que requests concurrentes funcionan."""
    from agents.orchestrator import Orchestrator
    
    orch = Orchestrator(session_id="e2e-concurrent")
    
    tasks = [
        orch.execute_user_request("investig"),
        orch.execute_user_request("valid"),
        orch.execute_user_request("codig"),
    ]
    
    results = await asyncio.gather(*tasks)
    
    assert all(r["status"] == "ok" for r in results)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
