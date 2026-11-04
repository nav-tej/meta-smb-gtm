"""Application settings. The only module that reads environment variables."""

import os
from functools import lru_cache

from dotenv import load_dotenv
from pydantic import BaseModel


class Settings(BaseModel):
    meta_model_api_key: str = ""
    meta_model_api_base_url: str = "https://api.meta.ai/v1"
    muse_spark_model: str = "muse-spark-1.3"
    muse_image_model: str = "muse-image-1.0"
    sam_model: str = "sam-3.1"

    comfyui_base_url: str = "http://127.0.0.1:8188"
    comfyui_api_key: str = ""

    meta_ads_access_token: str = ""
    meta_ad_account_id: str = ""

    crawler_user_agent: str = "MetaSMBGTM/0.1 (+https://github.com/nav-tej/meta-smb-gtm)"
    crawler_max_urls: int = 5000

    output_dir: str = "outputs"
    log_level: str = "INFO"

    # Demo mode serves saved live results so a public deployment can't spend Muse credits.
    # Live calls need ?live=true plus an X-Demo-Key header matching DEMO_KEY.
    demo_mode: bool = True
    demo_key: str = ""
    live_calls_per_hour: int = 5
    hosted_environment: bool = False


@lru_cache
def get_settings() -> Settings:
    load_dotenv()
    fields = Settings.model_fields
    values = {name: os.environ[name.upper()] for name in fields if os.environ.get(name.upper())}
    # Serverless filesystems (Vercel) are read-only except /tmp
    if os.environ.get("VERCEL") and "output_dir" not in values:
        values["output_dir"] = "/tmp/outputs"
    if os.environ.get("VERCEL"):
        values["hosted_environment"] = True
    return Settings(**values)
