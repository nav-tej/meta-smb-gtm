# Model inventory: open weights vs proprietary

Policy: prefer open-weight models run through ComfyUI. Use a hosted or proprietary API only where
no open option does the job (or the hackathon requires it), and list it here.

| Capability | Model | Open weights? | Runs where | Status |
|---|---|---|---|---|
| Segmentation | SAM 3.1 (`sam3.1_multiplex_fp16.safetensors`, Comfy-Org/sam3.1) | Yes | Local ComfyUI core node `SAM3_Detect` (`workflows/sam3_segment.json`) + Meta Model API `/v1/responses` fallback | Wired in `segment_product()` & `ComfyUIClient` |
| Reasoning / briefs | Muse Spark 1.3 | No public weights known | Meta Model API (hosted) | In use, required by hackathon judging |
| Image generation | Muse Image 1.0 | No public weights known | Meta Model API (hosted) | In use, required by hackathon judging |
| Scene relight | FLUX.1-Krea-dev, FLUX.1-Fill-dev | Yes (check FLUX.1 [dev] license terms before commercial use) | Local ComfyUI | In use |
| Style ref / typography / video | Krea-2 Turbo, Ideogram v4, LTX-2.5, MiniMax H3 (int8 weight files) | Weight files are loaded locally; licenses not yet verified | Local ComfyUI | In use |
| Scene restaging | Krea 3 (`Krea3ImageNode`, from `api_` template) | No: Comfy partner API, billed | Comfy partner proxy | In use; open-weight alternative preferred |
| Upscale | 4x-UltraSharp | Yes | Local ComfyUI | In use |
| App stack | FastAPI, Pydantic, httpx, defusedxml, ComfyUI | Open source | Local | In use |

TODO: verify each license from its model card before calling the stack "open source".
