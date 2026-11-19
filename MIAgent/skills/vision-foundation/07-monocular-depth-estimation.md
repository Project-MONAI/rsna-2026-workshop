# Monocular depth estimation

> Research snapshot verified through **2026-09-06**. Repository and pretrained-weight links point to official project sources; verify current checkpoint terms before use.

| Year | Model | Architecture / pretraining | Best use case | Repository | Pretrained weights | License/access | Maturity |
|---|---|---|---|---|---|---|---|
| 2025 | Depth Anything 3 | DINO-style encoder plus geometry prediction across arbitrary views | Current Depth Anything line and arbitrary-view geometry | [repo](https://github.com/ByteDance-Seed/Depth-Anything-3) | [official checkpoints](https://github.com/ByteDance-Seed/Depth-Anything-3) | Verify checkpoint terms | Released technical report |
| 2025 | MoGe-2 | ViT geometry encoder-decoder predicting metric point maps | Metric depth, intrinsics/FOV, normals, and point maps | [repo](https://github.com/microsoft/MoGe) | [official checkpoints](https://github.com/microsoft/MoGe) | MIT code | Released |
| 2024 | Depth Anything V2 | DINOv2 encoder plus DPT-style depth head | Mature zero-shot relative monocular depth | [repo](https://github.com/DepthAnything/Depth-Anything-V2) | [model zoo](https://github.com/DepthAnything/Depth-Anything-V2) | Apache-2.0 code; weight terms vary | Established released |
| 2024 | Depth Pro | ViT-based multi-scale metric depth system | Sharp metric monocular depth and focal length | [repo](https://github.com/apple/ml-depth-pro) | [checkpoint](https://github.com/apple/ml-depth-pro) | Apple model license | Established released |
| 2024 | Metric3D v2 | Canonical camera-space metric geometry | Cross-camera metric depth and normals | [repo](https://github.com/YvanYin/Metric3D) | [model zoo](https://github.com/YvanYin/Metric3D) | BSD-style code; verify weights | Established released |
| 2023 | ZoeDepth | MiDaS/DPT relative features plus metric-bin heads | Historical relative-to-metric monocular baseline | [repo](https://github.com/isl-org/ZoeDepth) | [checkpoints](https://github.com/isl-org/ZoeDepth) | MIT | Landmark baseline |
