# ComfyUI workflows

Workflow files used by the Ad Creative Studio for open-weight variant generation alongside Meta's `SAM 3.1`, `Muse Spark 1.3`, and `Muse Image 1.0`. Saved in ComfyUI's **API format** (`Workflow > Export (API)`).

For fine artists and handmade sellers (e.g., *Art of Sarabjit Singh*), `SAM 3.1` first segments the exact original painting/product so zero brushstrokes are altered or hallucinated, `Muse Image 1.0` produces the primary creative, and these open-weight ComfyUI workflows generate photorealistic collector wall staging, placement aspect-ratio outpaints (`4:5`, `9:16`, `1:1`), and print-grade upscales.

| Workflow | Input nodes | Open-weight models |
|---|---|---|
| `flux_krea_scene_relight.json` | `"1"` (`LoadImage.image`: artwork PNG), `"2"` (`LoadImageMask.image`: SAM 3.1 mask PNG), `"6"` (`CLIPTextEncode.text`: scene prompt), `"7"` (`EmptyLatentImage.width`/`height`) | `black-forest-labs/FLUX.1-Krea-dev` (`flux1-krea-dev.safetensors`), `t5xxl_fp8_e4m3fn.safetensors`, `clip_l.safetensors`, `ae.safetensors` |
| `placement_outpaint.json` | `"1"` (`LoadImage.image`: base creative PNG), `"5"` (`CLIPTextEncode.text`: outpaint prompt), `"6"` (`ImagePadForOutpaint.top`/`bottom`/`left`/`right`) | `black-forest-labs/FLUX.1-Fill-dev` (`flux1-fill-dev.safetensors`), `t5xxl_fp8_e4m3fn.safetensors`, `clip_l.safetensors`, `ae.safetensors` |
| `upscale_4x.json` | `"1"` (`LoadImage.image`: creative PNG) | `4x-UltraSharp.pth` |
