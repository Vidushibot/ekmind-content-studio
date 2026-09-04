from abc import ABC, abstractmethod
from pathlib import Path


class VoiceProvider(ABC):
    @abstractmethod
    def synthesize(self, text: str, output: Path) -> Path: ...


class MockVoiceProvider(VoiceProvider):
    def synthesize(self, text: str, output: Path) -> Path:
        output.write_text("MOCK: no external voice provider called", encoding="utf-8"); return output

