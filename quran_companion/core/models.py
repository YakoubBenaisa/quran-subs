"""Domain models. Plain dataclasses, no I/O."""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Reciter:
    id: int
    ar: str
    en: str
    style: str
    folder: str          # base URL of the whole-surah mp3 files
    count: int = 114     # surahs available

    @property
    def slug(self) -> str:
        return self.folder.rstrip("/").split("/audio/")[-1].replace("/", "_")

    @property
    def short_style(self) -> str:
        return self.style.replace("Rewayat ", "").replace("Almusshaf Al ", "").replace(" A'n ", " ʿan ")

    def name(self, rtl: bool) -> str:
        return self.ar if rtl else (self.en or self.ar)

    def search_text(self) -> str:
        return f"{self.en} {self.ar} {self.style}"


@dataclass(frozen=True)
class SurahInfo:
    number: int
    name: str            # Arabic, e.g. "سُورَةُ ٱلْفَاتِحَةِ"
    english: str
    meaning: str
    ayahs: int
    revelation: str      # "Meccan" | "Medinan"

    @property
    def short_name(self) -> str:
        return self.name.replace("سُورَةُ ", "")


@dataclass(frozen=True)
class Translation:
    id: str
    language: str
    name: str


@dataclass(frozen=True)
class Ayah:
    n: int
    ar: str
    tr: str = ""


@dataclass(frozen=True)
class VerseTiming:
    ayah: int            # 0 = intro (isti'adha / basmala)
    start_ms: int
    end_ms: int


@dataclass
class SurahData:
    """Everything a playback session needs for one surah."""
    surah: int
    ayahs: dict[int, Ayah]
    timings: list[VerseTiming] = field(default_factory=list)
    word_fracs: dict[int, dict[int, float]] = field(default_factory=dict)  # ayah -> word pos -> fraction


@dataclass
class Page:
    """One screenful of a verse: at most `max_lines` Quran lines (+ its share of the translation)."""
    lines: list[str]
    tr: list[str] = field(default_factory=list)
    w0: int = 0              # index of the first word on this page
    frac: float = 0.0        # where the page starts, as a fraction of the verse
    tr_scale: float = 1.0    # translation font scale chosen to fit
