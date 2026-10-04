"""Runtime failures carry fixed codes, never private configuration or Win32 text."""


class SecurityError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)
