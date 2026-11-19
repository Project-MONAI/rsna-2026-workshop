#!/usr/bin/env python3
"""One small GPU MONAI optimization step used to validate local tracking."""

from __future__ import annotations

import torch
from monai.networks.nets import UNet

from experiment_tracking import record_metric, record_parameters, record_telemetry


def main() -> None:
    device = torch.device("cuda")
    torch.manual_seed(7)
    model = UNet(spatial_dims=3, in_channels=1, out_channels=2, channels=(8, 16, 32), strides=(2, 2)).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-3)
    inputs = torch.randn(1, 1, 32, 32, 32, device=device)
    labels = torch.randint(0, 2, (1, 32, 32, 32), device=device)
    record_parameters({"workload": "synthetic_monai_smoke", "model": "UNet", "spatial_dims": 3})
    optimizer.zero_grad(set_to_none=True)
    loss = torch.nn.functional.cross_entropy(model(inputs), labels)
    loss.backward()
    optimizer.step()
    torch.cuda.synchronize()
    record_metric("train.loss", float(loss.detach().cpu()), step=1)
    record_telemetry({"gpu.memory_allocated_mb": torch.cuda.memory_allocated() / 1024**2}, step=1)
    print(f"synthetic MONAI smoke loss={loss.detach().item():.6f}")


if __name__ == "__main__":
    main()
