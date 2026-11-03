# ComfyUI Creative Workflows (Krea 3, Krea 2 Turbo, Ideogram 4, LTX-2.5 DFR, MiniMax H3)

This directory contains API-format ComfyUI workflow graphs (`POST /prompt` ready) used by `src/clients/comfyui.py` and `src/services/ad_creative.py`, plus the full UI-format gallery templates under `workflows/gallery/` fetched via `comfy templates fetch`.

## 1. Image Restaging, Relighting & Typography Workflows

| Workflow File | Primary Model / Checkpoint | Purpose |
|---|---|---|
| `krea3_scene_edit.json` | `Krea 3` (`Krea3ImageNode` from `api_krea3_image_edit`) | Targeted regional room restaging & collector lighting around the artwork, followed by `SAM 3.1` `ImageCompositeMasked` pixel preservation. |
| `krea2_turbo_style_ref.json` | `krea2_turbo_int8_convrot.safetensors` + `qwen3vl_4b_fp8_scaled.safetensors` (`krea2`) + `qwen_image_vae.safetensors` | High-speed 8-step open-weight MMDiT collector scene generation with style reference & `SAM 3.1` mask guard. |
| `ideogram4_collector_card.json` | `ideogram4_int8_convrot.safetensors` + `qwen3vl_8b_fp8_scaled.safetensors` (`ideogram4`) + `flux2-vae.safetensors` | Open-weight Ideogram v4 Int8 collector framing with razor-sharp exhibition plaque typography. |
| `flux_krea_scene_relight.json` | `flux1-krea-dev.safetensors` | Open-weight FLUX.1-Krea-dev room generation + `SAM 3.1` composite. |
| `placement_outpaint.json` | `flux1-fill-dev.safetensors` | Aspect-ratio outpainting (`1:1`, `4:5`, `9:16`) for Meta feed and story placements. |
| `upscale_4x.json` | `4x-UltraSharp.pth` | 4x print/high-DPI ad creative upscaling. |

## 2. Video Reels & Synchronized Audio Workflows (`9:16` / `4:5`)

| Workflow File | Primary Model / Checkpoints | Purpose |
|---|---|---|
| `ltx2_5_dfr_i2v.json` | `ltx-2.5-22b-distilled-transformer-comfy-int8-convrot.safetensors` + `gemma4-12b-with-proj-ltx-2.5-comfy-int8-convrot.safetensors` + `ltx-2.5-latent-spatial-upscaler-x2-bf16-1.0.safetensors` + `ltx-2.5-22b-ic-lora-pixel-spatial-upscaler-x2-1.0.safetensors` | Open-weight **LTX-2.5 Diffusion Fidelity Rendering (DFR)** Image-to-Video with x2 spatial detail pass and synchronized ambient audio (`LTXVAudioVAEDecode`). |
| `minimax_h3_i2v.json` | `minimax_h3_fl2va_pruned_int8_convrot.safetensors` + `minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors` + `qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors` + `minimax_h3_video_vae_int8_convrot.safetensors` + `minimax_h3_audio_vae_fp32.safetensors` | Open-weight **MiniMax H3** 8-step Turbo Image-to-Video generating cinematic camera motion and synchronized stereo audio (`VAEDecodeAudio`) in a single pass. |

## 3. Comfy CLI & Skills Integration

The official `comfy` CLI skills (`comfy`, `comfy-fragments`, `comfy-debug`, `comfy-relay`, `comfy-director`) are installed in `.claude/skills/`. You can inspect or run any workflow via:

```bash
comfy templates ls --model "Krea"
comfy templates ls --model "LTX-2.5"
comfy templates ls --model "MiniMax H3"
comfy run --workflow workflows/krea3_scene_edit.json
```
