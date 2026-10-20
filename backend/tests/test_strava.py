from backend.scripts.sync_strava_local import parse_elapsed_to_seconds


def test_parse_elapsed_to_seconds():
    assert parse_elapsed_to_seconds("10:42") == 642
    assert parse_elapsed_to_seconds("1:02:33") == 3753
    assert parse_elapsed_to_seconds("2h 3m 4s") == 7384
    assert parse_elapsed_to_seconds("") is None
    assert parse_elapsed_to_seconds("sin datos") is None
