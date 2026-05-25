"""Offline-style account management.

xd launcher uses offline / cracked-style accounts (nickname + UUID).
"""
from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from typing import List, Optional

from .paths import ACCOUNTS_FILE, ensure_dirs


def _offline_uuid(name: str) -> str:
    return str(uuid.uuid3(uuid.NAMESPACE_OID, f"OfflinePlayer:{name}"))


@dataclass
class Account:
    name: str
    uuid: str = ""
    token: str = "0"  # placeholder for offline auth

    def __post_init__(self) -> None:
        if not self.uuid:
            self.uuid = _offline_uuid(self.name)


@dataclass
class AccountStore:
    accounts: List[Account] = field(default_factory=list)

    @classmethod
    def load(cls) -> "AccountStore":
        ensure_dirs()
        if not ACCOUNTS_FILE.exists():
            return cls()
        try:
            data = json.loads(ACCOUNTS_FILE.read_text(encoding="utf-8"))
        except Exception:
            return cls()
        accs = [Account(**a) for a in data.get("accounts", [])]
        return cls(accounts=accs)

    def save(self) -> None:
        ensure_dirs()
        ACCOUNTS_FILE.write_text(
            json.dumps({"accounts": [asdict(a) for a in self.accounts]}, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def add(self, name: str) -> Account:
        name = name.strip()
        if not name:
            raise ValueError("Имя не может быть пустым")
        for a in self.accounts:
            if a.name.lower() == name.lower():
                return a
        acc = Account(name=name)
        self.accounts.append(acc)
        self.save()
        return acc

    def remove(self, name: str) -> None:
        self.accounts = [a for a in self.accounts if a.name != name]
        self.save()

    def get(self, name: str) -> Optional[Account]:
        for a in self.accounts:
            if a.name == name:
                return a
        return None
