# Computational pathology

> Research snapshot verified through **2026-09-06**. Repository and pretrained-weight links point to official project sources; verify current checkpoint terms before use.

| Year | Model | Architecture / pretraining | Best use case | Repository | Pretrained weights | License/access | Maturity |
|---|---|---|---|---|---|---|---|
| 2026 | GigaPath-Flash / GigaTIME-Flash | Distilled tile+slide transformer family | Efficient whole-slide and tumor-microenvironment analysis | [official page](https://www.microsoft.com/en-us/research/publication/gigapath-flash-and-gigatime-flash-efficient-pathology-foundation-models-for-whole-slide-and-tumor-microenvironment-analysis/) | Linked from official page | Apache-2.0 family | Released preprint |
| 2025 | UNI2-h | ViT-H pathology encoder; DINO-style SSL on 200M+ tiles | Strong general pathology tile features | [repo](https://github.com/mahmoodlab/UNI) | [gated weights](https://github.com/mahmoodlab/UNI) | Gated; verify terms | Established released |
| 2025 | CONCH v1.5 | Pathology image-text encoder | Text-aligned pathology retrieval and zero-shot transfer | [model card](https://huggingface.co/MahmoodLab/conchv1_5) | [weights](https://huggingface.co/MahmoodLab/conchv1_5) | Gated; noncommercial restrictions may apply | Released |
| 2024 | Virchow2 | ViT-H/14 modified DINOv2 trained on 3.1M WSIs | High-capacity pathology tile embeddings | [model card](https://huggingface.co/paige-ai/Virchow2) | [gated weights](https://huggingface.co/paige-ai/Virchow2) | CC-BY-NC-ND-4.0 | Established released |
| 2024 | H-optimus-1 | ViT-g self-supervised pathology tile encoder | Large-scale morphology features | [model card](https://huggingface.co/bioptimus/H-optimus-1) | [gated weights](https://huggingface.co/bioptimus/H-optimus-1) | Gated; verify terms | Released |
| 2024 | Prov-GigaPath | Tile encoder plus long-context slide transformer | Whole-slide representation and aggregation | [repo](https://github.com/prov-gigapath/prov-gigapath) | [official weights](https://github.com/prov-gigapath/prov-gigapath) | Apache-2.0 code; model terms | Established released |
