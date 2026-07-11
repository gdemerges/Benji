from benji.stt.postprocessing import postprocess_text


def test_empty():
    assert postprocess_text("") == ""
    assert postprocess_text("   ").strip() == ""


def test_capitalize_first():
    assert postprocess_text("bonjour") == "Bonjour"


def test_capitalize_after_period():
    assert postprocess_text("bonjour. ça va") == "Bonjour. Ça va"


def test_removes_french_hesitations():
    out = postprocess_text("euh je pense que, heu, oui")
    assert "euh" not in out.lower()
    assert "heu" not in out.lower()


def test_fix_french_apostrophe():
    assert postprocess_text("qu ' on parle") == "Qu'on parle"


def test_fix_hyphen():
    assert postprocess_text("est - ce que") == "Est-ce que"


def test_spacing_around_punctuation():
    out = postprocess_text("salut ,comment ça va ?")
    assert " ," not in out
    assert "?" in out


def test_english_contractions():
    out = postprocess_text("im sure i cant", language="en")
    assert "I'm" in out
    assert "can't" in out.lower() or "Can't" in out


def test_multiple_spaces_collapsed():
    assert "  " not in postprocess_text("hello    world")


def test_decimal_numbers_preserved():
    # Pas d'espace inséré entre deux chiffres (virgule ou point décimal).
    assert "2,5" in postprocess_text("il fait 2,5 degrés")
    assert "3.14" in postprocess_text("pi vaut 3.14 environ")


def test_eh_bien_preserved():
    # « eh », « ah », « oh » sont des mots légitimes en français.
    assert postprocess_text("eh bien voilà") == "Eh bien voilà"
    assert postprocess_text("ah bon, d'accord") == "Ah bon, d'accord"


def test_leading_hesitation_leaves_no_orphan_punctuation():
    # « Euh, oui » → suppression de l'hésitation → pas de « , oui » résiduel.
    assert postprocess_text("euh, oui") == "Oui"
