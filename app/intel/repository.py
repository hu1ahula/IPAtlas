from __future__ import annotations

from ipaddress import IPv4Network, IPv6Network
from threading import RLock
from typing import Iterable

from app.intel.cache import LookupCache
from app.intel.geo import GeoBackend, NullGeoBackend
from app.intel.ip_utils import ip_classification, parse_ip, parse_ip_range, parse_network, range_to_networks
from app.intel.merge import merge_records
from app.intel.prefix import PrefixIndex
from app.intel.types import PrefixRecord, SourceInfo


IPNetwork = IPv4Network | IPv6Network


class InMemoryIntelRepository:
    def __init__(
        self,
        records: Iterable[PrefixRecord] | None = None,
        sources: Iterable[SourceInfo] | None = None,
        geo_backend: GeoBackend | None = None,
        cache: LookupCache | None = None,
    ):
        self._lock = RLock()
        self._records: list[PrefixRecord] = list(records or [])
        self._sources: dict[str, SourceInfo] = {source.name: source for source in sources or []}
        self._index = PrefixIndex(self._records)
        self._geo_backend = geo_backend or NullGeoBackend()
        self._cache = cache
        self._records_version = 0

    @property
    def record_count(self) -> int:
        with self._lock:
            return len(self._records)

    def sources(self) -> list[dict]:
        with self._lock:
            known_sources = {
                record.source
                for record in self._records
                if record.source not in self._sources
            }
            for source in known_sources:
                source_records = [record for record in self._records if record.source == source]
                self._sources[source] = SourceInfo(
                    name=source,
                    source_type=source_records[0].source_type,
                    record_count=len(source_records),
                )
            source_infos = list(self._sources.values())
            geo_source = self._geo_backend.source_info()
            if geo_source is not None:
                source_infos.append(geo_source)
            return [source.to_dict() for source in sorted(source_infos, key=lambda item: item.name)]

    def lookup_ip(self, value: str, include_sources: bool = False) -> dict:
        ip = parse_ip(value)
        cache_key = self._cache_key(str(ip), include_sources)
        if self._cache is not None:
            cached = self._cache.get(cache_key)
            if cached is not None:
                return cached

        with self._lock:
            matches = self._index.lookup(ip)
        geo_match = self._geo_backend.lookup(ip)
        if geo_match is not None:
            matches.append(geo_match)
            matches = sorted(
                matches,
                key=lambda record: (record.priority, record.network.prefixlen, record.confidence),
                reverse=True,
            )
        merged = merge_records(matches, include_sources=include_sources)
        result = {
            **ip_classification(ip),
            **merged,
        }
        if self._cache is not None:
            self._cache.set(cache_key, result)
        return result

    def query_cidr(self, value: str) -> dict:
        network = parse_network(value)
        with self._lock:
            records = [record for record in self._records if record.overlaps(network)]
        return {
            "cidr": str(network),
            "ip_version": network.version,
            "record_count": len(records),
            "records": [record.to_summary() for record in self._sort_records(records)],
        }

    def query_range(self, start_ip: str, end_ip: str) -> dict:
        start, end = parse_ip_range(start_ip, end_ip)
        networks = range_to_networks(start_ip, end_ip)
        with self._lock:
            records = [
                record
                for record in self._records
                if record.network.version == start.version and any(record.overlaps(network) for network in networks)
            ]
        return {
            "start_ip": str(start),
            "end_ip": str(end),
            "ip_version": start.version,
            "record_count": len(records),
            "records": [record.to_summary() for record in self._sort_records(records)],
        }

    def query_asn(self, asn: int) -> dict:
        with self._lock:
            records = [record for record in self._records if record.asn == asn]
        return {
            "asn": asn,
            "record_count": len(records),
            "records": [record.to_summary() for record in self._sort_records(records)],
        }

    def replace_source(self, source: SourceInfo, records: Iterable[PrefixRecord]) -> None:
        new_records = list(records)
        for record in new_records:
            if record.source != source.name:
                raise ValueError(f"record source {record.source!r} does not match {source.name!r}")

        with self._lock:
            kept = [record for record in self._records if record.source != source.name]
            self._records = kept + new_records
            self._sources[source.name] = SourceInfo(
                **{
                    **source.to_dict(),
                    "updated_at": source.updated_at,
                    "record_count": len(new_records),
                }
            )
            self._index = PrefixIndex(self._records)
            self._records_version += 1
        if self._cache is not None:
            self._cache.clear_namespace()

    def geo_status(self) -> dict:
        return self._geo_backend.status()

    def reload_geo_backend(self) -> None:
        reload_method = getattr(self._geo_backend, "reload", None)
        if callable(reload_method):
            reload_method()
        if self._cache is not None:
            self._cache.clear_namespace()

    def close(self) -> None:
        close_geo = getattr(self._geo_backend, "close", None)
        if callable(close_geo):
            close_geo()
        if self._cache is not None:
            self._cache.close()

    def all_records(self) -> list[PrefixRecord]:
        with self._lock:
            return list(self._records)

    @staticmethod
    def _sort_records(records: list[PrefixRecord]) -> list[PrefixRecord]:
        return sorted(
            records,
            key=lambda record: (
                record.priority,
                record.network.version,
                record.network.prefixlen,
                str(record.network),
            ),
            reverse=True,
        )

    def _cache_key(self, ip: str, include_sources: bool) -> str:
        return (
            "ipatlas:lookup:"
            f"{self._records_version}:"
            f"{self._geo_backend.version_token}:"
            f"{int(include_sources)}:"
            f"{ip}"
        )
