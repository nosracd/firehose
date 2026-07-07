from aspn23_xtensor import TypeTimestamp


def test_create_timestamp():
    timestamp = TypeTimestamp(1)
    assert timestamp is not None


if __name__ == '__main__':
    test_create_timestamp()
