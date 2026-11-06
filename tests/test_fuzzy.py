from utilities import fuzzy


def test_accents_and_case_are_ignored():
    assert fuzzy.matches('jalapenos', 'Jalapeños')
    assert fuzzy.matches('JALAPEÑO', 'jalapeno, sliced')


def test_small_typos_match():
    assert fuzzy.matches('jalepeno', 'Jalapeños')
    assert fuzzy.matches('romane', 'Romaine')
    assert fuzzy.matches('chiken thigh', 'Roasted chicken thigh')


def test_no_false_hits_on_short_or_unrelated_words():
    assert not fuzzy.matches('kale', 'Pickled onion')
    assert not fuzzy.matches('cob', 'Cab sauce')      # 3 letters: exact only
    assert not fuzzy.matches('xyz', 'Kale')


def test_every_word_must_match_and_exact_ranks_first():
    assert fuzzy.matches('bowl salad', 'Harvest Bowl Salad')
    assert not fuzzy.matches('bowl tofu', 'Harvest Bowl Salad')
    assert fuzzy.score('kale', 'Kale') < fuzzy.score('kale', 'Baby kale') < fuzzy.score('kale', 'Kael')
