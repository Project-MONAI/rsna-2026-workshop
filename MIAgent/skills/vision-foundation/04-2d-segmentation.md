# 2D semantic, instance, and panoptic segmentation

> Research snapshot verified through **2026-09-06**. Repository and pretrained-weight links point to official project sources; verify current checkpoint terms before use.

| Year | Model | Architecture / pretraining | Best use case | Repository | Pretrained weights | License/access | Maturity |
|---|---|---|---|---|---|---|---|
| 2026 | SAM 3.1 | DETR-style concept detector plus promptable mask/tracking memory | Text/exemplar/visual-prompt image and video segmentation | [repo](https://github.com/facebookresearch/sam3) | [official checkpoints](https://github.com/facebookresearch/sam3) | Gated; SAM license | Released frontier |
| 2026 | RF-DETR Seg | Real-time DETR instance-segmentation system | Trainable real-time closed-set instance segmentation | [docs](https://rfdetr.roboflow.com/latest/) | [published checkpoints](https://rfdetr.roboflow.com/latest/) | Core licenses vary by size | Released |
| 2024 | SAM 2.1 | Hiera image encoder plus memory attention | Visual-prompt segmentation and tracking | [repo](https://github.com/facebookresearch/sam2) | [checkpoints](https://github.com/facebookresearch/sam2) | Apache-2.0 code; checkpoint terms | Established released |
| 2023 | OneFormer | Task-conditioned universal segmentation transformer | One model for semantic, instance, and panoptic segmentation | [repo](https://github.com/SHI-Labs/OneFormer) | [model zoo](https://github.com/SHI-Labs/OneFormer) | Apache-2.0 | Established released |
| 2023 | Mask DINO | Unified DETR-style detection and mask prediction | High-quality closed-set instance/panoptic segmentation | [repo](https://github.com/IDEA-Research/MaskDINO) | [model zoo](https://github.com/IDEA-Research/MaskDINO) | Apache-2.0 | Established released |
| 2022 | Mask2Former | Mask-classification transformer decoder | Strong semantic/instance/panoptic baseline | [repo](https://github.com/facebookresearch/Mask2Former) | [model zoo](https://github.com/facebookresearch/Mask2Former) | MIT | Landmark baseline |
