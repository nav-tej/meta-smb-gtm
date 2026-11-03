"""ComfyUI HTTP API client.

Loads a workflow JSON from workflows/, fills input node values, submits via POST /prompt,
polls /history/{prompt_id}, and fetches outputs via /view.

TODO:
- ComfyUIError
- run_workflow(name, inputs) -> list[bytes]
"""
