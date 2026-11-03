"""Flow 2: Ad Creative Studio.

Segments the product with SAM 3.1, has Muse Spark write a creative brief and prompts,
generates creatives with Muse Image, and optionally runs ComfyUI workflows for variants.

See AGENTS.md, section 4, "Flow 2".

TODO:
- segment_product(image) -> mask + cutout via src.clients.meta (SAM 3.1)
- write_brief(product, placement, brand_notes) -> CreativeBrief via Muse Spark
- generate_creatives(brief, cutout) -> list[Creative] via Muse Image
- run_variants(creatives, workflow_name) -> list[Creative] via src.clients.comfyui
- Output: CreativeSet (paths, prompts, suggested copy, producing model per image)
"""
