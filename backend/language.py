# Output-language selection (English by default) and source-language support checks.
from backend.config import SUPPORTED_LANGUAGES, Settings

_NAME_TO_CODE = {name.lower(): code for code, name in SUPPORTED_LANGUAGES.items()}


class UnsupportedLanguage(Exception):
    pass


def normalize(value: str | None) -> str | None:
    """Accept an ISO code ("tr") or a name ("turkish"); return the code, or None if unknown."""
    if not value:
        return None
    key = value.strip().lower()
    if key in SUPPORTED_LANGUAGES:
        return key
    return _NAME_TO_CODE.get(key)


def resolve_output_language(requested: str | None, settings: Settings) -> str:
    if not requested:
        return settings.default_output_language
    code = normalize(requested)
    if code is None:
        raise UnsupportedLanguage(f"'{requested}' is not a supported output language.")
    return code


def source_language_flags(detected: str | None) -> list[str]:
    if not detected:
        return ["Source language could not be detected; translation may be unreliable."]
    if normalize(detected) is None:
        return [f"Source language '{detected}' is not on the supported list; treat the transcript and translation as uncertain."]
    return []
