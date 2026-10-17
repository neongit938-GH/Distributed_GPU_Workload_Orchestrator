import os
import sys
import tempfile
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

# Ensure worker-agent directory is on sys.path
AGENT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if AGENT_DIR not in sys.path:
    sys.path.insert(0, AGENT_DIR)

import launcher
from launcher import app

client = TestClient(app)

# Helper script definitions
GOOD_SCRIPT = """
print("SUCCESS: Good script completed")
exit(0)
"""

BAD_SCRIPT = """
print("ERROR: Bad script failing")
exit(1)
"""

TIMEOUT_SCRIPT = """
import time
print("Starting timeout script...")
time.sleep(10)
print("This should not be reached")
exit(0)
"""

CPU_SCRIPT = """
import torch
print("SUCCESS: Running on CPU as expected")
exit(0)
"""

SYNTHETIC_SCRIPT = """
import torch
import time
import argparse
parser = argparse.ArgumentParser()
parser.add_argument('--mem-fraction', type=float, default=0.01)
parser.add_argument('--duration', type=int, default=1)
args = parser.parse_args()

print("SUCCESS: Synthetic work completed")
exit(0)
"""

# NVML mock helpers
def mock_nvml_device_get_handle_by_index(gpu_index):
    handle = MagicMock()
    handle.index = gpu_index
    return handle

def mock_nvml_device_get_utilization_rates(handle):
    util = MagicMock()
    util.gpu = 20  # 20% utilization default
    util.memory = 10
    return util

@pytest.fixture(autouse=True)
def setup_test_env(tmp_path, monkeypatch):
    """Sets up an isolated directory for allowed scripts and resets environment variables."""
    script_dir = tmp_path / "scripts"
    script_dir.mkdir(parents=True, exist_ok=True)
    
    # Write mock scripts
    (script_dir / "good_script.py").write_text(GOOD_SCRIPT)
    (script_dir / "bad_script.py").write_text(BAD_SCRIPT)
    (script_dir / "timeout_script.py").write_text(TIMEOUT_SCRIPT)
    (script_dir / "cpu_script.py").write_text(CPU_SCRIPT)
    (script_dir / "synthetic_workload.py").write_text(SYNTHETIC_SCRIPT)
    
    # Configure launcher module globals and environment
    monkeypatch.setenv("WORKER_ALLOWED_SCRIPT_ROOT", str(script_dir))
    monkeypatch.setenv("SCHEDULER_WORKER_TOKEN", "0123456789abcdef0123456789abcdef")
    monkeypatch.setenv("WORKER_ALLOW_NVML_BYPASS", "false")
    
    monkeypatch.setattr(launcher, "ALLOWED_SCRIPT_ROOT", str(script_dir))
    monkeypatch.setattr(launcher, "WORKER_ALLOW_NVML_BYPASS", False)
    
    yield

# ==================== TEST CASES ====================

def test_health_check():
    """Verify worker health check endpoint returns 200 OK."""
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

def test_valid_dispatch():
    """Verify dispatch succeeds and logs stdout for good script."""
    response = client.post(
        "/dispatch",
        json={
            "job_id": "test_valid_001",
            "script_path": "good_script.py",
            "gpu_indices": [],
            "memory_mb": 1,
            "timeout": 5
        },
        headers={"Authorization": "Bearer 0123456789abcdef0123456789abcdef"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["job_id"] == "test_valid_001"
    assert data["status"] == "completed"
    assert data["exit_code"] == 0
    assert "SUCCESS" in data["log_stdout"]

def test_missing_script():
    """Verify 400 Bad Request is returned when script does not exist."""
    response = client.post(
        "/dispatch",
        json={
            "job_id": "test_missing_001",
            "script_path": "nonexistent.py",
            "gpu_indices": [0],
            "memory_mb": 1,
            "timeout": 5
        },
        headers={"Authorization": "Bearer 0123456789abcdef0123456789abcdef"}
    )
    assert response.status_code == 400
    assert "not found" in response.json()["detail"].lower()

def test_invalid_path_traversal():
    """Verify path traversal outside allowed root returns 400 Bad Request."""
    response = client.post(
        "/dispatch",
        json={
            "job_id": "test_traversal_001",
            "script_path": "../../etc/passwd.py",
            "gpu_indices": [0],
            "memory_mb": 1,
            "timeout": 5
        },
        headers={"Authorization": "Bearer 0123456789abcdef0123456789abcdef"}
    )
    assert response.status_code == 400
    assert "outside the allowed root" in response.json()["detail"].lower()

def test_nonzero_exit_code():
    """Verify non-zero script exit code is captured as failed."""
    response = client.post(
        "/dispatch",
        json={
            "job_id": "test_bad_exit_001",
            "script_path": "bad_script.py",
            "gpu_indices": [],
            "memory_mb": 1,
            "timeout": 5
        },
        headers={"Authorization": "Bearer 0123456789abcdef0123456789abcdef"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["job_id"] == "test_bad_exit_001"
    assert data["status"] == "failed"
    assert data["exit_code"] == 1
    assert "ERROR" in data["log_stdout"]

def test_timeout_handling():
    """Verify process exceeding timeout is terminated and recorded as timeout."""
    response = client.post(
        "/dispatch",
        json={
            "job_id": "test_timeout_001",
            "script_path": "timeout_script.py",
            "gpu_indices": [],
            "memory_mb": 1,
            "timeout": 2
        },
        headers={"Authorization": "Bearer 0123456789abcdef0123456789abcdef"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["job_id"] == "test_timeout_001"
    assert data["status"] == "timeout"
    assert data["timeout_occurred"] is True

def test_nvml_insufficient_memory(monkeypatch):
    """Verify NVML pre-check rejects job when free memory is below requested memory_mb."""
    with patch("launcher.pynvml") as mock_pynvml:
        mock_pynvml.nvmlInit.return_value = None
        mock_pynvml.nvmlShutdown.return_value = None
        mock_pynvml.nvmlDeviceGetHandleByIndex.side_effect = mock_nvml_device_get_handle_by_index
        
        # Mock 1 MB free memory when job requests 2 MB
        mem_info = MagicMock()
        mem_info.free = 1 * 1024 * 1024
        mem_info.total = 8 * 1024 * 1024
        mock_pynvml.nvmlDeviceGetMemoryInfo.return_value = mem_info
        mock_pynvml.nvmlDeviceGetUtilizationRates.return_value = mock_nvml_device_get_utilization_rates(0)
        
        response = client.post(
            "/dispatch",
            json={
                "job_id": "test_nvml_mem_001",
                "script_path": "synthetic_workload.py",
                "gpu_indices": [0],
                "memory_mb": 2,
                "timeout": 5
            },
            headers={"Authorization": "Bearer 0123456789abcdef0123456789abcdef"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "rejected"
        assert "insufficient free memory" in data["reason"].lower()

def test_nvml_high_utilization(monkeypatch):
    """Verify NVML pre-check rejects job when GPU utilization exceeds 80% threshold."""
    with patch("launcher.pynvml") as mock_pynvml:
        mock_pynvml.nvmlInit.return_value = None
        mock_pynvml.nvmlShutdown.return_value = None
        mock_pynvml.nvmlDeviceGetHandleByIndex.side_effect = mock_nvml_device_get_handle_by_index
        
        # Mock sufficient memory
        mem_info = MagicMock()
        mem_info.free = 4 * 1024 * 1024
        mem_info.total = 8 * 1024 * 1024
        mock_pynvml.nvmlDeviceGetMemoryInfo.return_value = mem_info
        
        # Mock 90% utilization (> 80%)
        util_info = MagicMock()
        util_info.gpu = 90
        mock_pynvml.nvmlDeviceGetUtilizationRates.return_value = util_info
        
        response = client.post(
            "/dispatch",
            json={
                "job_id": "test_nvml_util_001",
                "script_path": "good_script.py",
                "gpu_indices": [0],
                "memory_mb": 1,
                "timeout": 5
            },
            headers={"Authorization": "Bearer 0123456789abcdef0123456789abcdef"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "rejected"
        assert "utilization" in data["reason"].lower()

def test_missing_nvml_fail_closed(monkeypatch):
    """Verify launcher fails closed (rejects GPU jobs) when NVML is unavailable and bypass is false."""
    monkeypatch.setattr(launcher, "NVML_AVAILABLE", False)
    monkeypatch.setattr(launcher, "WORKER_ALLOW_NVML_BYPASS", False)
    
    response = client.post(
        "/dispatch",
        json={
            "job_id": "test_nvml_missing_001",
            "script_path": "good_script.py",
            "gpu_indices": [0],
            "memory_mb": 1,
            "timeout": 5
        },
        headers={"Authorization": "Bearer 0123456789abcdef0123456789abcdef"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "rejected"
    assert "nvml library unavailable" in data["reason"].lower()

def test_missing_nvml_with_bypass(monkeypatch):
    """Verify launcher bypasses NVML check when WORKER_ALLOW_NVML_BYPASS=true."""
    monkeypatch.setattr(launcher, "NVML_AVAILABLE", False)
    monkeypatch.setattr(launcher, "WORKER_ALLOW_NVML_BYPASS", True)
    
    response = client.post(
        "/dispatch",
        json={
            "job_id": "test_nvml_bypass_001",
            "script_path": "good_script.py",
            "gpu_indices": [0],
            "memory_mb": 1,
            "timeout": 5
        },
        headers={"Authorization": "Bearer 0123456789abcdef0123456789abcdef"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed"
    assert data["exit_code"] == 0

def test_empty_gpu_indices_cpu_fallback():
    """Verify empty gpu_indices list launches on CPU without NVML checks."""
    response = client.post(
        "/dispatch",
        json={
            "job_id": "test_cpu_fallback_001",
            "script_path": "cpu_script.py",
            "gpu_indices": [],
            "memory_mb": 1,
            "timeout": 5
        },
        headers={"Authorization": "Bearer 0123456789abcdef0123456789abcdef"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["job_id"] == "test_cpu_fallback_001"
    assert data["status"] == "completed"
    assert data["exit_code"] == 0
    assert "SUCCESS" in data["log_stdout"]

def test_concurrent_jobs_isolation():
    """Verify concurrent jobs execute independently and produce distinct results."""
    import threading
    import time
    results = []

    def dispatch_job(suffix):
        res = client.post(
            "/dispatch",
            json={
                "job_id": f"concurrent_{suffix}_{int(time.time()*1000)}",
                "script_path": "synthetic_workload.py",
                "gpu_indices": [],
                "memory_mb": 1,
                "timeout": 10
            },
            headers={"Authorization": "Bearer 0123456789abcdef0123456789abcdef"}
        )
        results.append(res.json())

    t1 = threading.Thread(target=dispatch_job, args=("A",))
    t2 = threading.Thread(target=dispatch_job, args=("B",))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert len(results) == 2
    for r in results:
        assert r["status"] == "completed"
        assert r["exit_code"] == 0
        assert r["job_id"].startswith("concurrent_")
        assert "SUCCESS" in r["log_stdout"]
    assert results[0]["job_id"] != results[1]["job_id"]

def test_metadata_and_priority_preserved():
    """Verify optional priority and metadata fields are accepted by schema."""
    response = client.post(
        "/dispatch",
        json={
            "job_id": "test_metadata_001",
            "script_path": "good_script.py",
            "gpu_indices": [],
            "memory_mb": 1,
            "priority": 5,
            "metadata": {"user_id": "suryansh", "experiment": "test"},
            "timeout": 5
        },
        headers={"Authorization": "Bearer 0123456789abcdef0123456789abcdef"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed"
