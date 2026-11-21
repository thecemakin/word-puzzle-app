from collections.abc import Iterable
from pathlib import Path
from typing import Optional

from app.engine.errors import EngineError
from app.engine.locales import LanguagePack, get_language_pack


class Dictionary:
    """In-memory word validator backed by a frozenset for O(1) lookups."""

    def __init__(self, language_pack: LanguagePack, words: frozenset[str]) -> None:
        self._language_pack = language_pack
        self._words = words

    @property
    def language_code(self) -> str:
        return self._language_pack.code

    def __len__(self) -> int:
        return len(self._words)

    def __contains__(self, word: object) -> bool:
        if not isinstance(word, str):
            return False
        return self.is_valid(word)

    def is_valid(self, word: str) -> bool:
        normalized = self._language_pack.normalize(word)
        return len(normalized) >= 2 and normalized in self._words

    @classmethod
    def from_words(cls, language_code: str, words: Iterable[str]) -> "Dictionary":
        pack = get_language_pack(language_code)
        cleaned: set[str] = set()
        for raw in words:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            normalized = pack.normalize(line)
            if len(normalized) >= 2 and all(ch in pack.alphabet for ch in normalized):
                cleaned.add(normalized)
        return cls(language_pack=pack, words=frozenset(cleaned))

    @classmethod
    def from_file(cls, language_code: str, file_path: Path) -> "Dictionary":
        if not file_path.exists():
            raise FileNotFoundError(f"Dictionary file not found: {file_path}")
        with file_path.open("r", encoding="utf-8") as handle:
            return cls.from_words(language_code, handle)


class DictionaryManager:
    """Loads and caches language dictionaries in memory."""

    def __init__(self, dictionaries_dir: Optional[Path] = None) -> None:
        self._dictionaries_dir = dictionaries_dir or Path("data/dictionaries")
        self._dictionaries: dict[str, Dictionary] = {}

    def load_languages(self, language_codes: Iterable[str]) -> None:
        for code in language_codes:
            pack = get_language_pack(code)
            file_path = self._dictionaries_dir / pack.dictionary_filename
            self._dictionaries[pack.code] = Dictionary.from_file(pack.code, file_path)

    def register(self, dictionary: Dictionary) -> None:
        self._dictionaries[dictionary.language_code] = dictionary

    def get(self, language_code: str) -> Dictionary:
        pack = get_language_pack(language_code)
        dictionary = self._dictionaries.get(pack.code)
        if dictionary is None:
            raise EngineError(
                error_code="DICTIONARY_NOT_LOADED",
                message=f"Dictionary is not loaded for language '{pack.code}'",
                details={"language": pack.code},
            )
        return dictionary

    def is_valid_word(self, language_code: str, word: str) -> bool:
        return self.get(language_code).is_valid(word)

    @property
    def loaded_languages(self) -> list[str]:
        return list(self._dictionaries.keys())
