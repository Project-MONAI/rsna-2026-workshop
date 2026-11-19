# 3D object detection

> Research snapshot verified through **2026-09-06**. Repository and pretrained-weight links point to official project sources; verify current checkpoint terms before use.

This category mixes LiDAR/point-cloud, camera-only BEV, and monocular 3D detection. They are not directly comparable.

| Year | Model | Architecture / pretraining | Best use case | Repository | Pretrained weights | License/access | Maturity |
|---|---|---|---|---|---|---|---|
| 2026 | OVMono3D | Open-vocabulary monocular 3D detector with vision-language supervision | Novel-category 3D boxes from a single RGB image | [repo](https://github.com/UVA-Computer-Vision-Lab/ovmono3d) | [repo releases](https://github.com/UVA-Computer-Vision-Lab/ovmono3d) | Verify checkpoint terms | 3DV 2026, released frontier |
| 2024 | UniMODE | Unified monocular 3D detector across datasets/domains | Cross-domain camera-only 3D detection | [repo](https://github.com/Lizhuoling/UniMODE) | [model zoo](https://github.com/Lizhuoling/UniMODE) | Apache-2.0 | CVPR 2024, released |
| 2023 | Uni3DETR | Query-based unified 3D detector for point clouds | LiDAR/point-cloud 3D boxes across indoor/outdoor datasets | [repo](https://github.com/zhenyuw16/Uni3DETR) | [checkpoints](https://github.com/zhenyuw16/Uni3DETR) | Apache-2.0 | Released |
| 2023 | BEVFusion | Multimodal camera+LiDAR BEV fusion | Autonomous-driving multimodal 3D detection | [repo](https://github.com/mit-han-lab/bevfusion) | [model zoo](https://github.com/mit-han-lab/bevfusion) | Apache-2.0 | Established released |
| 2022 | BEVFormer | Spatiotemporal transformer producing BEV features from cameras | Camera-only autonomous-driving 3D detection | [repo](https://github.com/fundamentalvision/BEVFormer) | [checkpoints](https://github.com/fundamentalvision/BEVFormer) | Apache-2.0 | Established released |
| 2021 | CenterPoint | Center-based voxel/point-cloud detector | Robust LiDAR baseline and deployment comparator | [implementation](https://github.com/open-mmlab/mmdetection3d) | [MMDetection3D model zoo](https://github.com/open-mmlab/mmdetection3d) | Apache-2.0 | Landmark baseline |
