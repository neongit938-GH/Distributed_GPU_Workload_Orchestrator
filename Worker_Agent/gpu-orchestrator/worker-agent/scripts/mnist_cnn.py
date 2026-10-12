import argparse
import os
import time
import warnings

warnings.filterwarnings("ignore")

import torch
import torch.nn as nn
import torch.optim as optim
import torchvision
import torchvision.transforms as transforms


class LightweightCNN(nn.Module):
    """Lightweight Convolutional Neural Network for MNIST classification."""

    def __init__(self):
        super().__init__()
        self.features = nn.Sequential(
            nn.Conv2d(1, 16, kernel_size=3, padding=1),
            nn.ReLU(),
            nn.MaxPool2d(2),
            nn.Conv2d(16, 32, kernel_size=3, padding=1),
            nn.ReLU(),
            nn.MaxPool2d(2),
        )
        self.classifier = nn.Sequential(
            nn.Linear(32 * 7 * 7, 64),
            nn.ReLU(),
            nn.Linear(64, 10),
        )

    def forward(self, x):
        x = self.features(x)
        x = torch.flatten(x, 1)
        return self.classifier(x)


class SyntheticModel(nn.Module):
    """Linear model for synthetic tensor workloads."""

    def __init__(self):
        super().__init__()
        self.linear = nn.Linear(1024, 10)

    def forward(self, x):
        # Flatten input [batch_size, 32, 32] -> [batch_size, 1024]
        x = x.view(x.size(0), -1)
        return self.linear(x)


def parse_arguments():
    parser = argparse.ArgumentParser(description="Fairlane Lightweight Training & Verification Script")
    parser.add_argument("--epochs", type=int, default=2, help="Number of training epochs (default: 2)")
    parser.add_argument("--batch-size", type=int, default=64, help="Batch size (default: 64)")
    parser.add_argument(
        "--synthetic",
        action="store_true",
        help="Use synthetic tensor workload instead of downloading MNIST",
    )
    parser.add_argument("--log-interval", type=int, default=100, help="Batches between log outputs (default: 100)")
    parser.add_argument("--cpu", action="store_true", help="Force CPU execution regardless of GPU availability")
    parser.add_argument("--data-dir", type=str, default="./data", help="Directory for MNIST dataset storage")
    parser.add_argument(
        "--synthetic-batches",
        type=int,
        default=200,
        help="Number of batches per epoch for synthetic workload (default: 200)",
    )
    return parser.parse_args()


def get_device_info(force_cpu: bool):
    """Inspects device environment using torch.cuda or NVML physical device inspection."""
    if force_cpu:
        return {"cuda_available": False, "devices": [], "device_name": None}

    # If PyTorch natively supports CUDA, use torch.cuda
    if torch.cuda.is_available():
        visible_count = torch.cuda.device_count()
        if visible_count > 0:
            current_dev = torch.cuda.current_device()
            dev_name = torch.cuda.get_device_name(current_dev)
            return {
                "cuda_available": True,
                "visible_count": visible_count,
                "current_device": current_dev,
                "device_name": dev_name,
            }
        return {"cuda_available": False, "devices": [], "device_name": None}

    # Fallback to NVML if torch wheel is CPU-only but physical GPU exists
    cuda_env = os.environ.get("CUDA_VISIBLE_DEVICES")
    try:
        import pynvml
        pynvml.nvmlInit()
        total_nvml_devs = pynvml.nvmlDeviceGetCount()
        
        # Parse CUDA_VISIBLE_DEVICES
        if cuda_env is not None:
            if not cuda_env.strip():
                # Empty CUDA_VISIBLE_DEVICES forces CPU
                pynvml.nvmlShutdown()
                return {"cuda_available": False, "devices": [], "device_name": None}
            
            requested_indices = []
            for part in cuda_env.split(","):
                part = part.strip()
                if part.isdigit():
                    requested_indices.append(int(part))
        else:
            requested_indices = list(range(total_nvml_devs))

        valid_devices = []
        for idx in requested_indices:
            if 0 <= idx < total_nvml_devs:
                handle = pynvml.nvmlDeviceGetHandleByIndex(idx)
                name = pynvml.nvmlDeviceGetName(handle)
                if isinstance(name, bytes):
                    name = name.decode("utf-8")
                valid_devices.append({"index": idx, "name": name})

        pynvml.nvmlShutdown()

        if valid_devices:
            return {
                "cuda_available": True,
                "visible_count": len(valid_devices),
                "current_device": 0,
                "device_name": valid_devices[0]["name"],
            }
    except Exception:
        pass

    return {"cuda_available": False, "devices": [], "device_name": None}


def print_environment_report(dev_info: dict):
    print(f"[INFO] PyTorch version: {torch.__version__}", flush=True)
    cuda_available = dev_info.get("cuda_available", False)
    print(f"[INFO] CUDA available: {cuda_available}", flush=True)
    if cuda_available:
        print(f"[INFO] Visible GPU count: {dev_info.get('visible_count', 0)}", flush=True)
        print(f"[INFO] Current device: {dev_info.get('current_device', 0)}", flush=True)
        print(f"[INFO] GPU name: {dev_info.get('device_name')}", flush=True)
    else:
        print("[INFO] Running on CPU", flush=True)


def train_synthetic(model, optimizer, criterion, device, epochs, batch_size, batches_per_epoch, log_interval):
    print("[INFO] Generating synthetic tensor workload...")
    print(f"[INFO] Input shape per batch: [{batch_size}, 32, 32], Target classes: 10")
    total_start_time = time.time()
    final_loss = 0.0

    for epoch in range(1, epochs + 1):
        model.train()
        for batch_idx in range(1, batches_per_epoch + 1):
            data = torch.randn(batch_size, 32, 32, device=device)
            target = torch.randint(0, 10, (batch_size,), dtype=torch.long, device=device)

            optimizer.zero_grad()
            output = model(data)
            loss = criterion(output, target)
            loss.backward()
            optimizer.step()

            final_loss = loss.item()
            if batch_idx == 1 or batch_idx % log_interval == 0 or batch_idx == batches_per_epoch:
                print(f"[INFO] Epoch {epoch} [{batch_idx}/{batches_per_epoch}] Loss: {final_loss:.4f}")

    total_time = time.time() - total_start_time
    return total_time, final_loss


def train_mnist(model, optimizer, criterion, device, epochs, batch_size, data_dir, log_interval):
    print("[INFO] Loading MNIST dataset...")
    transform = transforms.Compose([
        transforms.ToTensor(),
        transforms.Normalize((0.1307,), (0.3081,)),
    ])

    try:
        os.makedirs(data_dir, exist_ok=True)
        train_dataset = torchvision.datasets.MNIST(
            root=data_dir,
            train=True,
            download=True,
            transform=transform,
        )
        train_loader = torch.utils.data.DataLoader(
            train_dataset,
            batch_size=batch_size,
            shuffle=True,
        )
    except Exception as e:
        print(f"[WARNING] Failed to load/download MNIST dataset ({e}). Falling back to synthetic workload.")
        synthetic_model = SyntheticModel().to(device)
        synthetic_opt = optim.Adam(synthetic_model.parameters(), lr=0.001)
        return train_synthetic(
            synthetic_model,
            synthetic_opt,
            criterion,
            device,
            epochs,
            batch_size,
            batches_per_epoch=200,
            log_interval=log_interval,
        )

    total_batches = len(train_loader)
    total_start_time = time.time()
    final_loss = 0.0

    for epoch in range(1, epochs + 1):
        model.train()
        for batch_idx, (data, target) in enumerate(train_loader, start=1):
            data, target = data.to(device), target.to(device)

            optimizer.zero_grad()
            output = model(data)
            loss = criterion(output, target)
            loss.backward()
            optimizer.step()

            final_loss = loss.item()
            if batch_idx == 1 or batch_idx % log_interval == 0 or batch_idx == total_batches:
                print(f"[INFO] Epoch {epoch} [{batch_idx}/{total_batches}] Loss: {final_loss:.4f}")

    total_time = time.time() - total_start_time
    return total_time, final_loss


def main():
    args = parse_arguments()

    dev_info = get_device_info(args.cpu)
    print_environment_report(dev_info)

    # Device-agnostic assignment (relies on torch device)
    device = torch.device("cuda" if torch.cuda.is_available() and not args.cpu else "cpu")
    print(f"[INFO] Starting training on device: {device}", flush=True)

    criterion = nn.CrossEntropyLoss()

    if args.synthetic:
        model = SyntheticModel().to(device)
        optimizer = optim.Adam(model.parameters(), lr=0.001)
        time_elapsed, final_loss = train_synthetic(
            model=model,
            optimizer=optimizer,
            criterion=criterion,
            device=device,
            epochs=args.epochs,
            batch_size=args.batch_size,
            batches_per_epoch=args.synthetic_batches,
            log_interval=args.log_interval,
        )
    else:
        model = LightweightCNN().to(device)
        optimizer = optim.Adam(model.parameters(), lr=0.001)
        time_elapsed, final_loss = train_mnist(
            model=model,
            optimizer=optimizer,
            criterion=criterion,
            device=device,
            epochs=args.epochs,
            batch_size=args.batch_size,
            data_dir=args.data_dir,
            log_interval=args.log_interval,
        )

    print(f"[INFO] Total training time: {time_elapsed:.2f}s")
    print(f"[INFO] Final loss: {final_loss:.4f}")
    print(f"[INFO] Device used: {device}")


if __name__ == "__main__":
    main()
