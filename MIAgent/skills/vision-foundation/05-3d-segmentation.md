# 3D and volumetric segmentation

> Research snapshot verified through **2026-09-06**. Repository and pretrained-weight links point to official project sources; verify current checkpoint terms before use.

| Year | Model | Architecture / pretraining | Best use case | Repository | Pretrained weights | License/access | Maturity |
|---|---|---|---|---|---|---|---|
| 2026 | UniMedSeg | Sequence model unifying visual in-context, geometric, and language prompts | Unified prompted 2D/3D medical segmentation | [paper](https://arxiv.org/abs/2607.12896) | Reported by authors; verify current release | Verify before use | Preprint |
| 2026 | Medical SAM3 V2 | SAM3 adapted to 2D and native 3D medical data | Heterogeneous medical promptable segmentation | [repo](https://github.com/AIM-Research-Lab/Medical-SAM3) | [2D/3D weights](https://github.com/AIM-Research-Lab/Medical-SAM3) | Verify model/data terms | Released preprint |
| 2026 | VoxTell v1.1 | 3D vision-language segmentation model | Free-text-to-volume masks in CT/MRI/PET | [repo](https://github.com/MIC-DKFZ/VoxTell) | [v1.1 checkpoint](https://github.com/MIC-DKFZ/VoxTell) | Verify checkpoint/data terms | CVPR 2026, released |
| 2025 | Sonata + task head | Self-supervised Point Transformer V3 encoder | Point-cloud semantic/instance transfer | [repo](https://github.com/facebookresearch/sonata) | [pretrained weights](https://github.com/facebookresearch/sonata) | Code Apache-2.0; weights CC-BY-NC-4.0 | CVPR 2025 Highlight |
| 2024 | VISTA3D | SegResNet/point-prompted 3D medical segmentation system | Automatic and interactive CT segmentation | [repo](https://github.com/Project-MONAI/VISTA) | [MONAI bundles](https://github.com/Project-MONAI/VISTA) | NVIDIA/MONAI terms | Established released |
| 2023 | OpenScene | 2D-language features lifted/fused into 3D | Open-vocabulary 3D point/scene segmentation | [repo](https://github.com/pengsongyou/openscene) | [checkpoints](https://github.com/pengsongyou/openscene) | MIT | CVPR 2023, released |
| 2021/2024 | nnU-Net v2 | Self-configuring U-Net pipeline | Mandatory closed-set 3D medical baseline | [repo](https://github.com/MIC-DKFZ/nnUNet) | Task-trained weights via model sharing, not one universal checkpoint | Apache-2.0 | Standard baseline |
