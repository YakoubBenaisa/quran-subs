import pytest

from quran_companion.core.guess import guess_reciter, guess_surah

TITLES = [
    ("سورة الكهف كاملة - مشاري العفاسي", 18, "Alafasi"),
    ("Surah Al-Kahf | Mishary Rashid Alafasy", 18, "Alafasi"),
    ("Yasser Al Dossary - Surat Yasin", 36, "Dosari"),
    ("سورة يس ياسر الدوسري", 36, "Dosari"),
    ("018 Al-Kahf.mp3", 18, None),
    ("Surah Al-Baqarah Full - Saad Al Ghamdi", 2, None),
    ("سورة الملك بصوت عبد الباسط عبد الصمد", 67, "Abdulsamad"),
    ("Surah Ar-Rahman (The Beneficent)", 55, None),
    ("سورة ق | ماهر المعيقلي", 50, None),
    ("Relaxing nature sounds", None, None),
]


@pytest.mark.parametrize("title,surah,reciter", TITLES)
def test_guess(repo, title, surah, reciter):
    assert guess_surah(title, repo.surahs()) == surah
    r = guess_reciter(title, repo.reciters())
    if reciter: assert r is not None and reciter.lower() in r.en.lower(), r


def test_clean_title():
    from quran_companion.core.guess import clean_title
    assert clean_title("Surat Al-Mulk (The Sovereignty) | Mishary Rashid Alafasy | مشاري بن راشد العفاسي | سورة الملك") == \
        "Surat Al-Mulk (The Sovereignty) · Mishary Rashid Alafasy"
    t = clean_title("Surah Al-Mulk full || By Sheikh Sudais With Arabic Text (HD) |سورة الملك|")
    assert t.startswith("Surah Al-Mulk full · By Sheikh Sudais")
    assert len(clean_title("x" * 200)) == 70
