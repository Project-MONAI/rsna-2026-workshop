# Multiview 3D reconstruction and geometry

> Research snapshot verified through **2026-09-06**. Repository and pretrained-weight links point to official project sources; verify current checkpoint terms before use.

| Year | Model | Architecture / pretraining | Best use case | Repository | Pretrained weights | License/access | Maturity |
|---|---|---|---|---|---|---|---|
| 2026 | VGGT-Ω | Permutation-equivariant multiview transformer with one dense head | Static and dynamic feed-forward reconstruction | [repo](https://github.com/facebookresearch/vggt-omega) | [official checkpoints](https://github.com/facebookresearch/vggt-omega) | Verify checkpoint terms | CVPR 2026 Oral |
| 2026 | VGG-T³ | VGGT-style model with per-scene test-time training | Reconstruction when adaptation compute is available | [repo](https://github.com/nv-dvl/vgg-ttt) | [repo checkpoints](https://github.com/nv-dvl/vgg-ttt) | Verify terms | CVPR 2026 frontier |
| 2025 | MapAnything | Flexible transformer accepting varied geometry observations | Reconstruction with mixed camera/depth/geometry inputs | [repo](https://github.com/facebookresearch/map-anything) | [official checkpoints](https://github.com/facebookresearch/map-anything) | Verify checkpoint terms | Released frontier |
| 2025 | π³ | Permutation-equivariant, reference-free multiview transformer | Reconstruction without choosing a reference frame | [paper](https://arxiv.org/abs/2507.13347) | Verify current author release | Verify before use | Preprint/revised 2026 |
| 2025 | VGGT | Feed-forward transformer for cameras, depth, point maps, and tracks | Established general multiview reconstruction baseline | [repo](https://github.com/facebookresearch/vggt) | [official checkpoints](https://github.com/facebookresearch/vggt) | Custom checkpoint terms | CVPR 2025, released |
| 2024 | MASt3R | DUSt3R-style point maps plus local feature matching | Image matching and reconstruction initialization | [repo](https://github.com/naver/mast3r) | [official checkpoints](https://github.com/naver/mast3r) | CC BY-NC-SA model terms | Established released |
| 2024 | DUSt3R | Pairwise transformer regressing aligned point maps | Foundational learned pairwise reconstruction | [repo](https://github.com/naver/dust3r) | [official checkpoints](https://github.com/naver/dust3r) | CC BY-NC-SA model terms | Landmark baseline |
