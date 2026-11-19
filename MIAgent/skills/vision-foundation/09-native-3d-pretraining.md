# Native 3D / point-cloud representation pretraining

> Research snapshot verified through **2026-09-06**. Repository and pretrained-weight links point to official project sources; verify current checkpoint terms before use.

| Year | Model | Architecture / pretraining | Best use case | Repository | Pretrained weights | License/access | Maturity |
|---|---|---|---|---|---|---|---|
| 2026 | MASS | Mask-guided in-context SSL over CT/MRI/PET volumes | Spatially grounded 3D medical encoder pretraining | [paper](https://arxiv.org/abs/2603.13660) | Verify official release from paper | Verify before use | CVPR 2026 frontier |
| 2025 | Sonata | Point Transformer V3 self-supervised pretraining | Reusable indoor/outdoor point-cloud features | [repo](https://github.com/facebookresearch/sonata) | [pretrained weights](https://github.com/facebookresearch/sonata) | Code Apache-2.0; weights CC-BY-NC-4.0 | CVPR 2025 Highlight |
| 2024 | VoCo | Volumetric contextual-position contrastive learning | General 3D medical transfer | [repo](https://github.com/Luffy03/VoCo) | [checkpoints](https://github.com/Luffy03/VoCo) | Verify code/weight terms | Established released |
| 2023 | Point Transformer V3 | Serialized-neighborhood point transformer | Efficient point-cloud backbone | [repo](https://github.com/Pointcept/PointTransformerV3) | [model zoo](https://github.com/Pointcept/PointTransformerV3) | MIT | Established architecture |
| 2023 | PPT | Point-prompt training across heterogeneous 3D datasets | Supervised multi-dataset point-cloud pretraining | [repo](https://github.com/Pointcept/PointPromptTraining) | [checkpoints](https://github.com/Pointcept/PointPromptTraining) | MIT | Established released |
