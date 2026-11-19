# 2D image classification and general representation

> Research snapshot verified through **2026-09-06**. Repository and pretrained-weight links point to official project sources; verify current checkpoint terms before use.

| Year | Model | Architecture / pretraining | Best use case | Repository | Pretrained weights | License/access | Maturity |
|---|---|---|---|---|---|---|---|
| 2026 | EUPE | Efficient ViT/ConvNeXt students distilled from PEcore, PElang, and DINOv3 | Small reusable semantic+dense encoders | [repo](https://github.com/facebookresearch/eupe) | [releases in repo](https://github.com/facebookresearch/eupe) | Verify checkpoint terms | Released frontier |
| 2026 | LingBot-Vision | ViT; boundary-centric masked modeling | Boundary-sensitive dense representation and transfer | [repo](https://github.com/Robbyant/lingbot-vision) | [model zoo](https://github.com/Robbyant/lingbot-vision) | Apache-2.0 code; verify weights | Released preprint |
| 2025 | DINOv3 | ViT-S to 7B and ConvNeXt; self-distillation/dense SSL | Strong frozen dense features and general transfer | [repo](https://github.com/facebookresearch/dinov3) | [official checkpoints](https://github.com/facebookresearch/dinov3) | Meta checkpoint terms | Established released |
| 2025 | Perception Encoder | ViT PEcore/PElang/PEspatial variants | Recognition, language-aligned, or spatial transfer | [repo](https://github.com/facebookresearch/perception_models) | [model zoo](https://github.com/facebookresearch/perception_models) | Verify per checkpoint | Released frontier |
| 2025 | SigLIP 2 | ViT image-text encoder with multilingual/localization/SSL signals | Retrieval, zero-shot classification, VLM vision tower | [official model](https://huggingface.co/google/siglip2-base-patch16-224) | [Hugging Face weights](https://huggingface.co/google/siglip2-base-patch16-224) | Apache-2.0 model card | Established released |
| 2024 | RADIOv2.5 / RADIO Amplified | ViT multi-teacher distillation | One encoder spanning semantic and dense transfer | [repo](https://github.com/NVlabs/RADIO) | [checkpoints](https://github.com/NVlabs/RADIO) | NVIDIA terms; verify checkpoint | Established released |
| 2023 | DINOv2 | ViT; curated-data self-distillation | Mature general image baseline | [repo](https://github.com/facebookresearch/dinov2) | [official checkpoints](https://github.com/facebookresearch/dinov2) | Apache-2.0 code; model terms | Established released |
