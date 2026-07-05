from __future__ import annotations

import hashlib
from collections import Counter
from ipaddress import IPv4Network, IPv6Network
from threading import Lock, RLock
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
        self._mutation_lock = Lock()
        self._records: list[PrefixRecord] = list(records or [])
        self._sources: dict[str, SourceInfo] = {source.name: source for source in sources or []}
        self._index = PrefixIndex(self._records)
        self._asn_index = self._build_asn_index(self._records)
        self._geo_backend = geo_backend or NullGeoBackend()
        self._cache = cache
        self._records_version = 0
        self._prefix_snapshot_status: dict[str, object] = {"status": "not_started"}

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

    def query_cidr(self, value: str, limit: int = 100, offset: int = 0) -> dict:
        network = parse_network(value)
        with self._lock:
            records = [record for record in self._records if record.overlaps(network)]
        page = self._paginate_records(self._sort_records(records), limit=limit, offset=offset)
        return {
            "cidr": str(network),
            "ip_version": network.version,
            "record_count": len(records),
            **page,
        }

    def query_range(self, start_ip: str, end_ip: str, limit: int = 100, offset: int = 0) -> dict:
        start, end = parse_ip_range(start_ip, end_ip)
        networks = range_to_networks(start_ip, end_ip)
        with self._lock:
            records = [
                record
                for record in self._records
                if record.network.version == start.version and any(record.overlaps(network) for network in networks)
            ]
        page = self._paginate_records(self._sort_records(records), limit=limit, offset=offset)
        return {
            "start_ip": str(start),
            "end_ip": str(end),
            "ip_version": start.version,
            "record_count": len(records),
            **page,
        }

    def query_asn(self, asn: int, limit: int = 100, offset: int = 0) -> dict:
        with self._lock:
            records = list(self._asn_index.get(asn, []))
        page = self._paginate_records(self._sort_records(records), limit=limit, offset=offset)
        return {
            "asn": asn,
            "record_count": len(records),
            **page,
        }

    def replace_source(self, source: SourceInfo, records: Iterable[PrefixRecord]) -> None:
        self.replace_sources([source], records)

    def replace_sources(
        self,
        sources: Iterable[SourceInfo],
        records: Iterable[PrefixRecord],
    ) -> None:
        new_sources = list(sources)
        new_records = list(records)
        source_names = {source.name for source in new_sources}
        for record in new_records:
            if record.source not in source_names:
                raise ValueError(f"record source {record.source!r} has no matching SourceInfo")

        with self._mutation_lock:
            with self._lock:
                kept = [record for record in self._records if record.source not in source_names]
                source_map = dict(self._sources)

            all_records = kept + new_records
            new_index = PrefixIndex(all_records)
            new_asn_index = self._build_asn_index(all_records)
            record_counts = Counter(record.source for record in new_records)
            for source in new_sources:
                source_map[source.name] = SourceInfo(
                    **{
                        **source.to_dict(),
                        "updated_at": source.updated_at,
                        "record_count": record_counts[source.name],
                    }
                )

            with self._lock:
                self._records = all_records
                self._sources = source_map
                self._index = new_index
                self._asn_index = new_asn_index
                self._records_version += 1
        if self._cache is not None:
            self._cache.clear_namespace()

    def set_prefix_snapshot_status(self, status: dict[str, object]) -> None:
        with self._lock:
            self._prefix_snapshot_status = dict(status)

    def prefix_snapshot_status(self) -> dict[str, object]:
        with self._lock:
            return dict(self._prefix_snapshot_status)

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

    @staticmethod
    def _build_asn_index(records: list[PrefixRecord]) -> dict[int, list[PrefixRecord]]:
        index: dict[int, list[PrefixRecord]] = {}
        for record in records:
            asn = record.asn
            if asn is None:
                continue
            index.setdefault(asn, []).append(record)
        return index

    @staticmethod
    def _paginate_records(records: list[PrefixRecord], limit: int, offset: int) -> dict:
        total_count = len(records)
        page = records[offset : offset + limit]
        return {
            "total_count": total_count,
            "returned_count": len(page),
            "limit": limit,
            "offset": offset,
            "truncated": offset + len(page) < total_count,
            "records": [record.to_summary() for record in page],
        }

    def _cache_key(self, ip: str, include_sources: bool) -> str:
        return (
            "ipatlas:lookup:"
            f"{self._prefix_version_token()}:"
            f"{self._geo_backend.version_token}:"
            f"{int(include_sources)}:"
            f"{ip}"
        )

    def _prefix_version_token(self) -> str:
        with self._lock:
            digest = hashlib.sha256()
            digest.update(str(self._records_version).encode())
            for source in sorted(self._sources.values(), key=lambda item: item.name):
                digest.update(source.name.encode())
                digest.update(b":")
                digest.update(source.version.encode())
                digest.update(b":")
                digest.update(str(source.metadata.get("checksum") or "").encode())
                digest.update(b"\0")
            return digest.hexdigest()[:20]
