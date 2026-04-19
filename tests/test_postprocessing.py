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
