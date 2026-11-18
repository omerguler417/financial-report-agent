# Shared exceptions. ProviderNotConfigured names the service and the exact settings to add, so every unconfigured service produces a clear setup message.


class ProviderNotConfigured(Exception):
    def __init__(self, service: str, missing: list[str], how: str):
        self.service, self.missing, self.how = service, list(missing), how
        super().__init__(f"{service} is not configured. Add {', '.join(missing)} to .env and restart the server. {how}")

    def to_dict(self) -> dict:
        return {"service": self.service, "missing": self.missing, "how_to_configure": self.how}
