from __future__ import annotations

from dataclasses import dataclass, field
from ipaddress import IPv4Address, IPv6Address

from app.intel.types import PrefixRecord


IPAddress = IPv4Address | IPv6Address


@dataclass
class _TrieNode:
    children: dict[int, "_TrieNode"] = field(default_factory=dict)
    records: list[PrefixRecord] = field(default_factory=list)


class PrefixTrie:
    def __init__(self, ip_version: int):
        self.ip_version = ip_version
        self.max_bits = 32 if ip_version == 4 else 128
        self.root = _TrieNode()

    def insert(self, record: PrefixRecord) -> None:
        if record.ip_version != self.ip_version:
            raise ValueError("record IP version does not match trie")
        node = self.root
        network_value = int(record.network.network_address)
        for bit_index in range(record.network.prefixlen):
            bit = (network_value >> (self.max_bits - bit_index - 1)) & 1
            node = node.children.setdefault(bit, _TrieNode())
        node.records.append(record)

    def lookup(self, ip: IPAddress) -> list[PrefixRecord]:
        if ip.version != self.ip_version:
            return []
        node = self.root
        matches = list(node.records)
        ip_value = int(ip)
        for bit_index in range(self.max_bits):
            bit = (ip_value >> (self.max_bits - bit_index - 1)) & 1
            node = node.children.get(bit)
            if node is None:
                break
            matches.extend(node.records)
        return matches


class PrefixIndex:
    def __init__(self, records: list[PrefixRecord] | None = None):
        self._records: list[PrefixRecord] = []
        self._tries = {4: PrefixTrie(4), 6: PrefixTrie(6)}
        for record in records or []:
            self.insert(record)

    @property
    def records(self) -> list[PrefixRecord]:
        return list(self._records)

    def insert(self, record: PrefixRecord) -> None:
        self._records.append(record)
        self._tries[record.ip_version].insert(record)

    def lookup(self, ip: IPAddress) -> list[PrefixRecord]:
        records = self._tries[ip.version].lookup(ip)
        return sorted(
            records,
            key=lambda record: (record.priority, record.network.prefixlen, record.confidence),
            reverse=True,
        )

