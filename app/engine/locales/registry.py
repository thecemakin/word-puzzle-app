from app.engine.errors import EngineError
from app.engine.locales.base import LanguagePack
from app.engine.locales.en import EN_PACK
from app.engine.locales.tr import TR_PACK

_LANGUAGE_REGISTRY: dict[str, LanguagePack] = {}


def register_language(pack: LanguagePack) -> None:
    _LANGUAGE_REGISTRY[pack.code.lower()] = pack


def get_language_pack(code: str) -> LanguagePack:
    normalized = code.strip().lower()
    pack = _LANGUAGE_REGISTRY.get(normalized)
    if pack is None:
        raise EngineError(
            error_code="UNSUPPORTED_LANGUAGE",
            message=f"Unsupported game language: '{code}'",
            details={"language": code, "supported": sorted(_LANGUAGE_REGISTRY.keys())},
        )
    return pack


def list_language_packs() -> list[LanguagePack]:
    return list(_LANGUAGE_REGISTRY.values())


def supported_language_codes() -> list[str]:
    return list(_LANGUAGE_REGISTRY.keys())


# Built-in starter languages
register_language(TR_PACK)
register_language(EN_PACK)
