import pytest

from revisa.packs.construction import field_matches, normalise


@pytest.mark.parametrize(
    ("field", "expected", "actual"),
    [
        ("revision", "A", "Rev. A"),
        ("revision", "B", "REVISION b"),
        ("drawing_number", "A-201", "DWG NO. A-201"),
        ("drawing_number", "5187114", "5187 114"),
        ("title", "First, second, mezz. & third floor", "FIRST SECOND MEZZ & THIRD FLOOR"),
        ("sheet_number", 1, "1"),
    ],
)
def test_equivalent_forms_match(field, expected, actual):
    assert field_matches(field, expected, actual)


@pytest.mark.parametrize(
    ("field", "expected", "actual"),
    [("revision", "A", "B"), ("drawing_number", "A-201", "A-210"), ("title", "Roof plan", None)],
)
def test_different_values_do_not_match(field, expected, actual):
    assert not field_matches(field, expected, actual)


def test_blank_is_none():
    assert normalise("title", "   ") is None
