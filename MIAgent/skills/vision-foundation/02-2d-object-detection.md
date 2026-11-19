# 2D object detection

> Research snapshot verified through **2026-09-06**. Repository and pretrained-weight links point to official project sources; verify current checkpoint terms before use.

| Year | Model | Architecture / pretraining | Best use case | Repository | Pretrained weights | License/access | Maturity |
|---|---|---|---|---|---|---|---|
| 2026 | RF-DETR | Real-time DETR with DINOv2 backbone | Custom closed-set real-time detection; also instance segmentation | [docs/repo](https://rfdetr.roboflow.com/latest/) | [published checkpoints](https://rfdetr.roboflow.com/latest/) | Core through Large Apache-2.0; larger tiers have separate terms | ICLR 2026, released |
| 2025 | D-FINE | DETR with fine-grained distribution refinement | Accurate real-time closed-set detection | [repo](https://github.com/Peterande/D-FINE) | [model zoo](https://github.com/Peterande/D-FINE) | Apache-2.0 | ICLR 2025 Spotlight |
| 2025 | RT-DETRv3 | Real-time DETR with improved dense positive supervision | Real-time end-to-end detector baseline | [repo](https://github.com/lyuwenyu/RT-DETR) | [model zoo](https://github.com/lyuwenyu/RT-DETR) | Apache-2.0 | WACV 2025, released |
| 2024 | Grounding DINO 1.5/1.6 line | Language-conditioned transformer detector | Open-vocabulary text-to-box localization | [canonical repo](https://github.com/IDEA-Research/GroundingDINO) | [weights](https://github.com/IDEA-Research/GroundingDINO) | Apache-2.0 code; verify commercial checkpoint/service terms | Established released |
| 2023 | DINO detector | Deformable DETR with denoising anchors and mixed queries | High-quality closed-set DETR baseline | [repo](https://github.com/IDEA-Research/DINO) | [model zoo](https://github.com/IDEA-Research/DINO) | Apache-2.0 | Established released |
| 2021 | Deformable DETR | Sparse multiscale deformable attention | Historical efficient DETR baseline | [repo](https://github.com/fundamentalvision/Deformable-DETR) | [checkpoints](https://github.com/fundamentalvision/Deformable-DETR) | Apache-2.0 | Landmark baseline |
| 2020 | DETR | Encoder-decoder transformer with object queries and bipartite matching | Architectural reference and controlled baseline | [repo](https://github.com/facebookresearch/detr) | [model zoo](https://github.com/facebookresearch/detr) | Apache-2.0 | Landmark baseline |
