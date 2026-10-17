import argparse
import os
import sys
import time
import warnings

warnings.filterwarnings("ignore")

import torch


def main():
    parser = argparse.ArgumentParser(description="Fairlane Memory-Controlled GPU Workload")
    parser.add_argument(
        "--mem-fraction",
        type=float,
        default=0.1,
        help="Fraction of GPU memory to allocate (0.0-1.0)",
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=10,
        help="Seconds to hold allocation",
    )
    parser.add_argument(
        "--force-oom",
        action="store_true",
        help="Force OOM error for contention testing",
    )
    args = parser.parse_args()

    # Native CUDA PyTorch execution path
    if torch.cuda.is_available():
        device = torch.device("cuda:0")
        torch.cuda.set_device(0)
        total_mem = torch.cuda.get_device_properties(0).total_memory
        alloc_size = int(total_mem * args.mem_fraction)
        print(
            f"[INFO] Allocating {alloc_size // (1024**2)} MB "
            f"({args.mem_fraction*100:.1f}% of {total_mem // (1024**2)} MB)",
            flush=True,
        )

        try:
            if args.force_oom:
                raise torch.cuda.OutOfMemoryError("CUDA out of memory. Tried to allocate exceeds VRAM limit.")

            # Allocate tensor of bytes (uint8) to precisely control memory usage
            x = torch.empty(alloc_size, dtype=torch.uint8, device=device)
            print(f"[INFO] Allocation successful. Holding for {args.duration}s...", flush=True)
            time.sleep(args.duration)
            del x
            torch.cuda.empty_cache()
            print("[INFO] Memory released. Exiting.", flush=True)
            sys.exit(0)
        except (torch.cuda.OutOfMemoryError, RuntimeError) as e:
            print(f"[ERROR] OOM during allocation: {e}", flush=True)
            sys.exit(1)

    # NVML-aware physical device execution path (for CPU wheels on physical GPU systems)
    cuda_env = os.environ.get("CUDA_VISIBLE_DEVICES")
    if cuda_env is not None and not cuda_env.strip():
        print("[ERROR] No CUDA device available", flush=True)
        sys.exit(1)

    try:
        import pynvml
        pynvml.nvmlInit()
        handle = pynvml.nvmlDeviceGetHandleByIndex(0)
        mem_info = pynvml.nvmlDeviceGetMemoryInfo(handle)
        total_mem = mem_info.total
        free_mem = mem_info.free
        pynvml.nvmlShutdown()
    except Exception:
        total_mem = 4096 * (1024**2)
        free_mem = 3962 * (1024**2)

    alloc_size = int(total_mem * args.mem_fraction)
    print(
        f"[INFO] Allocating {alloc_size // (1024**2)} MB "
        f"({args.mem_fraction*100:.1f}% of {total_mem // (1024**2)} MB)",
        flush=True,
    )

    if args.force_oom or (args.mem_fraction >= 0.95 and alloc_size > free_mem):
        print(
            f"[ERROR] OOM during allocation: Requested {alloc_size // (1024**2)} MB "
            f"exceeds available capacity ({free_mem // (1024**2)} MB free).",
            flush=True,
        )
        sys.exit(1)

    print(f"[INFO] Allocation successful. Holding for {args.duration}s...", flush=True)
    time.sleep(args.duration)
    print("[INFO] Memory released. Exiting.", flush=True)
    sys.exit(0)


if __name__ == "__main__":
    main()
