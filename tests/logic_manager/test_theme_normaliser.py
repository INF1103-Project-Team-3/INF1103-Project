import pytest

from managers.logic_manager.theme_normaliser import ThemeNormaliser
from managers.models import THEMES, UNCLEAR_THEME


@pytest.fixture
def normaliser():
    return ThemeNormaliser()


@pytest.mark.parametrize("theme", THEMES)
def test_each_base_theme_maps_to_itself(normaliser, theme):
    assert normaliser.normalise(theme) == theme


@pytest.mark.parametrize("label, theme", [
    ("wifi", "Facilities"),
    ("Lecturers", "Teaching Quality"),
    ("exams", "Assessment"),
    ("IWSP", "Internship Placement"),
])
def test_alias_maps_to_its_base_theme(normaliser, label, theme):
    assert normaliser.normalise(label) == theme


@pytest.mark.parametrize("label", ["Wi-Fi", "  WI_FI ", "wi.fi"])
def test_case_spacing_and_punctuation_are_ignored(normaliser, label):
    assert normaliser.normalise(label) == "Facilities"


@pytest.mark.parametrize("label", ["workload", "Heavy workload", "deadlines"])
def test_workload_is_its_own_theme_not_well_being(normaliser, label):
    assert normaliser.normalise(label) == "Workload"


@pytest.mark.parametrize("label", ["n/a", "other", "Spam", "misc.", "", "   "])
def test_unclear_words_and_blank_labels_become_unclear(normaliser, label):
    assert normaliser.normalise(label) == UNCLEAR_THEME


def test_unknown_label_becomes_a_new_theme_in_title_case(normaliser):
    assert normaliser.normalise("parking fees") == "Parking Fees"


def test_labels_that_differ_only_in_punctuation_give_the_same_new_theme(normaliser):
    assert normaliser.normalise("car-park") == normaliser.normalise("CAR PARK") == "Car Park"


def test_confirmed_theme_is_returned_as_stored(normaliser):
    normaliser.set_known_themes(["CCA Clubs"])
    assert normaliser.normalise("cca-clubs") == "CCA Clubs"


def test_base_themes_are_known_and_new_labels_are_not(normaliser):
    assert normaliser.is_known("facilities")
    assert not normaliser.is_known("Parking Fees")
    assert not normaliser.is_known(UNCLEAR_THEME)


def test_a_confirmed_theme_becomes_known(normaliser):
    normaliser.set_known_themes(["Parking Fees"])
    assert normaliser.is_known("parking-fees")


def test_is_new_only_for_a_real_label_that_is_not_known_yet(normaliser):
    assert normaliser.is_new("parking fees")
    assert not normaliser.is_new("Facilities")
    assert not normaliser.is_new("wifi")    # an alias of Facilities
    assert not normaliser.is_new(UNCLEAR_THEME)
    assert not normaliser.is_new("n/a")
    normaliser.set_known_themes(["Parking Fees"])
    assert not normaliser.is_new("parking fees")


def test_set_known_themes_replaces_confirmed_themes_but_keeps_base_ones(normaliser):
    normaliser.set_known_themes(["Car Park"])
    normaliser.set_known_themes(["Parking Fees"])
    assert not normaliser.is_known("Car Park")
    assert normaliser.is_known("Facilities")


def test_blank_or_unclear_labels_are_never_confirmed(normaliser):
    normaliser.set_known_themes(["Other", "  "])
    assert normaliser.normalise("other") == UNCLEAR_THEME
    assert normaliser.known_themes == THEMES


def test_known_themes_lists_base_then_confirmed_without_duplicates(normaliser):
    # data.load_known_themes() returns the base themes too, so they must not repeat
    normaliser.set_known_themes([*THEMES, "Car Park"])
    assert normaliser.known_themes == (*THEMES, "Car Park")


def test_default_known_themes_are_the_base_themes(normaliser):
    assert normaliser.known_themes == THEMES
