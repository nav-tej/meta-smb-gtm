"""Meta Model API client (Muse Spark, Muse Image, SAM 3.1).

The single place that talks to api.meta.ai. Uses the OpenAI-compatible SDK with base_url
overridden. Verify model IDs and the image/segmentation endpoint shapes before implementing
(AGENTS.md, section 3).

TODO:
- MetaAPIError
- chat_structured(messages, response_model) -> response_model instance (Muse Spark)
- generate_image(prompt, reference_image=None) -> bytes (Muse Image)
- segment(image, prompt=None) -> mask bytes (SAM 3.1)
"""
