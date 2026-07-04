from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="IPATLAS_", env_file=".env", extra="ignore")

    app_name: str = "IPAtlas"
    environment: str = "local"
    admin_token: str = Field(default="change-me", min_length=1)
    data_dir: Path = Path("./data")
    batch_max_size: int = Field(default=1000, ge=1, le=10000)
    enable_scheduler: bool = False
    geo_provider: str = "dbip_lite"
    dbip_download_page: str = "https://db-ip.com/db/download/ip-to-city-lite"
    dbip_mmdb_path: Path = Path("./data/dbip-city-lite.mmdb")
    lookup_cache_ttl_seconds: int = Field(default=86400, ge=0)
    auto_download_geo: bool = False
    iptoasn_combined_url: str = "https://iptoasn.com/data/ip2asn-combined.tsv.gz"
    aws_ip_ranges_url: str = "https://ip-ranges.amazonaws.com/ip-ranges.json"
    google_cloud_ranges_url: str = "https://www.gstatic.com/ipranges/cloud.json"
    azure_service_tags_page: str = "https://www.microsoft.com/en-us/download/details.aspx?id=56519"
    azure_service_tags_url: str | None = None
    azure_verify_tls: bool = True
    cloudflare_ipv4_url: str = "https://www.cloudflare.com/ips-v4"
    cloudflare_ipv6_url: str = "https://www.cloudflare.com/ips-v6"
    github_meta_url: str = "https://api.github.com/meta"
    sync_prefix_records_to_database: bool = True
    prefix_db_sync_batch_size: int = Field(default=5000, ge=100, le=50000)
    database_url: str = "postgresql+psycopg://ipatlas:ipatlas@localhost:5432/ipatlas"
    redis_url: str = "redis://localhost:6379/0"


@lru_cache
def get_settings() -> Settings:
    return Settings()
