class ExternalServiceError(RuntimeError):
    def __init__(self, service: str, message: str):
        super().__init__(f"{service}: {message}")
        self.service = service
        self.message = message


class MissingConfigurationError(RuntimeError):
    def __init__(self, setting: str):
        super().__init__(f"Missing required configuration: {setting}")
        self.setting = setting

