# Architecture and pretraining recipe index

> Research snapshot verified through **2026-09-06**. Repository and pretrained-weight links point to official project sources; verify current checkpoint terms before use.

| Year | Name | Type | Best use case | Repository / paper | Pretrained weights | Notes |
|---|---|---|---|---|---|---|
| 2026 | V-JEPA 2.1 | Dense video latent prediction recipe | Temporal/dense video representation | [repo](https://github.com/facebookresearch/vjepa2) | Yes | Compare with image-only DINOv3 |
| 2026 | MASS | Mask-guided 3D in-context SSL | Volumetric spatial semantics | [paper](https://arxiv.org/abs/2603.13660) | Verify release | Medical 3D-specific |
| 2026 | EUPE | Multi-teacher scale-up/scale-down distillation | Efficient universal encoders | [repo](https://github.com/facebookresearch/eupe) | Yes | Teacher mixture matters |
| 2025 | DINOv3 | Image self-distillation/dense SSL | Frozen spatial features at scale | [repo](https://github.com/facebookresearch/dinov3) | Yes | Recipe and checkpoints, not a new architecture class |
| 2025 | SigLIP 2 | Image-text contrastive/localization/SSL recipe | Language-aligned vision | [model](https://huggingface.co/google/siglip2-base-patch16-224) | Yes | Multilingual |
| 2023 | ConvNeXt V2 + FCMAE | CNN architecture plus fully convolutional masked autoencoding | Modern CNN control and efficient dense transfer | [repo](https://github.com/facebookresearch/ConvNeXt-V2) | [model zoo](https://github.com/facebookresearch/ConvNeXt-V2) | Latest verified named ConvNeXt architecture version |
| 2023 | DINOv2 | Image self-distillation recipe | Mature SSL baseline | [repo](https://github.com/facebookresearch/dinov2) | Yes | Superseded in-line by DINOv3 |
| 2022 | Swin V2 | Hierarchical shifted-window transformer | Multiscale dense backbone | [repo](https://github.com/microsoft/Swin-Transformer) | [model zoo](https://github.com/microsoft/Swin-Transformer) | Architecture, not pretraining recipe |
| 2020 | ViT | Patch transformer architecture | Scalable general vision backbone | [repo](https://github.com/google-research/vision_transformer) | [checkpoints](https://github.com/google-research/vision_transformer) | Architecture substrate |
