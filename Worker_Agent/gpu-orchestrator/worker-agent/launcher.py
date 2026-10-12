import asyncio
import logging
import os
import subprocess
import sys
import tempfile
import warnings
from typing import List, Literal, Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

warnings.filterwarnings("ignore", category=FutureWarning, module="pynvml")

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("worker-launcher")

app = FastAPI(
    title="Fairlane Worker Agent Launcher",
    description="GPU Workload Dispatch and Remote Execution Launcher",
    version="1.0.0",
)

# Configuration from environment variables
DEFAULT_ALLOWED_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "scripts"))
ALLOWED_SCRIPT_ROOT = os.path.abspath(
    os.environ.get("WORKER_ALLOWED_SCRIPT_ROOT", DEFAULT_ALLOWED_ROOT)
)

DEFAULT_LOG_DIR = os.path.abspath(
    os.environ.get(
        "WORKER_LOG_DIR",
        "/tmp" if os.name != "nt" else os.path.join(os.path.dirname(__file__), "logs"),
    )
)
os.makedirs(DEFAULT_LOG_DIR, exist_ok=True)

PYTHON_EXECUTABLE = os.environ.get("WORKER_PYTHON_BIN", sys.executable)

# NVML availability and bypass handling
WORKER_ALLOW_NVML_BYPASS = os.getenv("WORKER_ALLOW_NVML_BYPASS", "false").lower() == "true"
try:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=FutureWarning)
        import pynvml
    NVML_AVAILABLE = True
except ImportError:
    NVML_AVAILABLE = False
    if not WORKER_ALLOW_NVML_BYPASS:
        logger.error("pynvml library not available and bypass not allowed; GPU jobs will be rejected.")

class DispatchRequest(BaseModel):
    job_id: str
    script_path: str  # Absolute or relative to WORKER_ALLOWED_SCRIPT_ROOT
    gpu_indices: List[int] = Field(default_factory=list)  # e.g., [0] or [0, 1]
    timeout: int  # Seconds to wait before killing process
    memory_mb: int  # Required free memory per GPU in MB
    priority: Optional[int] = Field(default=0)  # Optional priority indicator
    metadata: Optional[dict] = Field(default_factory=dict)  # Optional free-form metadata
    args: List[str] = Field(default_factory=list)  # Optional CLI arguments for script

class DispatchResponse(BaseModel):
    job_id: str
    status: Literal["completed", "failed", "timeout", "rejected"]
    exit_code: int
    log_stdout: str
    log_stderr: str
    timeout_occurred: bool
    reason: Optional[str] = None

class CompletionCallback(BaseModel):
    job_id: str
    status: Literal["completed", "failed", "rejected", "timeout"]
    exit_code: int  # Process exit code (0 = success)
    log_output: str  # Combined tail of stdout/stderr (max 500 chars)
    gpus_used: List[int]  # Confirmed GPUs used (must match request)
    timestamp: str  # ISO 8601 UTC
    error_message: Optional[str] = None  # Present only if status in [failed, rejected, timeout]

def validate_dispatch_request(req: DispatchRequest) -> str:
    """Validates the dispatch request parameters and returns the resolved script path."""
    if not req.job_id or not req.job_id.strip():
        raise HTTPException(status_code=400, detail="Invalid job_id: must not be empty.")

    if req.timeout <= 0:
        raise HTTPException(status_code=400, detail="Invalid timeout: must be a positive integer.")

    for idx in req.gpu_indices:
        if not isinstance(idx, int) or idx < 0:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid gpu_indices: '{idx}' is not a non-negative integer.",
            )

    # Resolve script path
    allowed_root = os.path.realpath(ALLOWED_SCRIPT_ROOT)
    if os.path.isabs(req.script_path):
        resolved_script = os.path.realpath(req.script_path)
    else:
        resolved_script = os.path.realpath(os.path.join(allowed_root, req.script_path))

    # Path traversal validation
    try:
        common = os.path.commonpath([allowed_root, resolved_script])
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Script path '{req.script_path}' is on a different drive or invalid path.",
        )

    if common != allowed_root:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Access denied: script path '{req.script_path}' is outside the allowed root "
                f"'{allowed_root}'."
            ),
        )

    # File existence and type checks
    if not resolved_script.endswith(".py"):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid script file '{req.script_path}': must be a Python (.py) file.",
        )

    if not os.path.isfile(resolved_script):
        raise HTTPException(
            status_code=400,
            detail=f"Script '{req.script_path}' not found at resolved location '{resolved_script}'.",
        )

    return resolved_script

def read_tail(file_path: str, max_lines: int = 200, max_chars: int = 2000) -> str:
    """Reads the tail of a log file up to max_lines or max_chars."""
    if not os.path.exists(file_path):
        return ""
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
            tail_lines = lines[-max_lines:]
            content = "".join(tail_lines)
            if len(content) > max_chars:
                return content[-max_chars:]
            return content
    except Exception as e:
        logger.warning(f"Error reading tail from {file_path}: {e}")
        return ""

def check_gpu_resources(gpu_indices: List[int], required_mb: int, utilization_thresh: int = 80) -> Optional[str]:
    """Check each GPU for free memory and utilization.
    Returns None if all GPUs pass, otherwise returns a reason string.
    """
    if not gpu_indices:
        # No GPU required
        return None
    if not NVML_AVAILABLE:
        if WORKER_ALLOW_NVML_BYPASS:
            logger.warning("NVML not available; bypassing GPU checks as per configuration.")
            return None
        else:
            return "NVML library unavailable; GPU validation required."
    try:
        pynvml.nvmlInit()
        for idx in gpu_indices:
            try:
                handle = pynvml.nvmlDeviceGetHandleByIndex(idx)
                mem_info = pynvml.nvmlDeviceGetMemoryInfo(handle)
                free_mb = mem_info.free // (1024 * 1024)
                if free_mb < required_mb:
                    return f"GPU {idx}: insufficient free memory ({free_mb}MB < {required_mb}MB)"
                util = pynvml.nvmlDeviceGetUtilizationRates(handle)
                if util.gpu > utilization_thresh:
                    return f"GPU {idx}: utilization {util.gpu}% > {utilization_thresh}%"
            except pynvml.NVMLError as e:
                return f"GPU {idx}: NVML error: {str(e)}"
    finally:
        if NVML_AVAILABLE:
            try:
                pynvml.nvmlShutdown()
            except Exception:
                pass
    return None

def run_process_job(
    job_id: str,
    script_path: str,
    gpu_indices: List[int],
    timeout: int,
    args: Optional[List[str]] = None,
) -> DispatchResponse:
    """Synchronous process execution runner called via asyncio thread pool."""
    if args is None:
        args = []
    cuda_visible = ",".join(str(idx) for idx in gpu_indices)
    proc_env = {
        **os.environ,
        "CUDA_VISIBLE_DEVICES": cuda_visible,
        "PYTHONUNBUFFERED": "1",
    }

    stdout_path = os.path.join(DEFAULT_LOG_DIR, f"job_{job_id}.out")
    stderr_path = os.path.join(DEFAULT_LOG_DIR, f"job_{job_id}.err")

    cmd = [PYTHON_EXECUTABLE, script_path] + args
    logger.info(
        f"Dispatching job '{job_id}' | Command: {' '.join(cmd)} | "
        f"CUDA_VISIBLE_DEVICES='{cuda_visible}' | Timeout: {timeout}s"
    )

    timeout_occurred = False
    returncode = -1

    with open(stdout_path, "w", encoding="utf-8") as out_f, open(stderr_path, "w", encoding="utf-8") as err_f:
        proc = subprocess.Popen(
            cmd,
            stdout=out_f,
            stderr=err_f,
            env=proc_env,
        )
        try:
            returncode = proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            logger.warning(f"Job '{job_id}' exceeded timeout ({timeout}s). Terminating process.")
            timeout_occurred = True
            proc.kill()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
            returncode = -9  # Conventional SIGKILL exit code

    # Determine status
    if timeout_occurred:
        status: Literal["completed", "failed", "timeout", "rejected"] = "timeout"
    elif returncode == 0:
        status = "completed"
    else:
        status = "failed"

    log_stdout = read_tail(stdout_path)
    log_stderr = read_tail(stderr_path)

    logger.info(f"Job '{job_id}' finished with status='{status}', exit_code={returncode}")

    return DispatchResponse(
        job_id=job_id,
        status=status,
        exit_code=returncode,
        log_stdout=log_stdout,
        log_stderr=log_stderr,
        timeout_occurred=timeout_occurred,
        reason=None,
    )

@app.get("/healthz")
async def health_check():
    """Liveness probe endpoint."""
    return {"status": "ok"}

def create_callback_payload(request: DispatchRequest, response: DispatchResponse) -> CompletionCallback:
    """Creates a CompletionCallback payload conforming to Vansh Sagar's interface contract."""
    from datetime import datetime, timezone
    
    combined_log = (response.log_stdout + "\n" + response.log_stderr).strip()
    truncated_log = combined_log[-500:] if len(combined_log) > 500 else combined_log
    
    error_msg = None
    if response.status in ["failed", "rejected", "timeout"]:
        error_msg = response.reason or response.log_stderr.strip() or f"Job finished with status '{response.status}'"

    return CompletionCallback(
        job_id=request.job_id,
        status=response.status,
        exit_code=response.exit_code,
        log_output=truncated_log,
        gpus_used=request.gpu_indices,
        timestamp=datetime.now(timezone.utc).isoformat(),
        error_message=error_msg,
    )

async def send_scheduler_callback(callback_payload: CompletionCallback):
    """Sends completion callback to SCHEDULER_CALLBACK_URL if configured."""
    callback_url = os.environ.get("SCHEDULER_CALLBACK_URL")
    if not callback_url:
        return
    token = os.environ.get("SCHEDULER_WORKER_TOKEN", "")
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        import httpx
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(callback_url, json=callback_payload.model_dump(), headers=headers)
            logger.info(f"Callback delivered to {callback_url} [HTTP {resp.status_code}]")
    except Exception as e:
        logger.warning(f"Failed to deliver callback to {callback_url}: {e}")


@app.post("/dispatch", response_model=DispatchResponse)
async def dispatch_job(request: DispatchRequest):
    """Dispatches and executes a job with GPU isolation and timeout handling."""
    resolved_script = validate_dispatch_request(request)

    # Perform NVML pre-dispatch checks
    rejection_reason = check_gpu_resources(request.gpu_indices, request.memory_mb)
    if rejection_reason:
        logger.warning(f"Job '{request.job_id}' rejected: {rejection_reason}")
        rej_resp = DispatchResponse(
            job_id=request.job_id,
            status="rejected",
            exit_code=-1,
            log_stdout="",
            log_stderr="",
            timeout_occurred=False,
            reason=rejection_reason,
        )
        await send_scheduler_callback(create_callback_payload(request, rej_resp))
        return rej_resp

    # Execute in background thread to prevent blocking FastAPI event loop
    response = await asyncio.to_thread(
        run_process_job,
        request.job_id,
        resolved_script,
        request.gpu_indices,
        request.timeout,
        request.args,
    )
    await send_scheduler_callback(create_callback_payload(request, response))
    return response

@app.post("/dispatch-with-callback", response_model=CompletionCallback)
async def dispatch_with_callback(request: DispatchRequest):
    """Dispatches a job and converts output directly into a CompletionCallback contract response."""
    resp = await dispatch_job(request)
    return create_callback_payload(request, resp)

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("WORKER_PORT", 8000))
    host = os.environ.get("WORKER_HOST", "0.0.0.0")
    uvicorn.run("launcher:app", host=host, port=port, reload=False)

