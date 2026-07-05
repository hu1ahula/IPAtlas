import sys


def test_cli_update_dbip_does_not_load_prefix_snapshots(monkeypatch, capsys):
    import main

    def fail_load(_data_dir):
        raise AssertionError("CLI update should not preload prefix snapshots")

    monkeypatch.setattr(sys, "argv", ["ipatlas", "update", "dbip-city-lite"])
    monkeypatch.setattr("main.load_prefix_snapshots", fail_load, raising=False)
    monkeypatch.setattr(
        "main.update_source_from_local_file",
        lambda _repo, source: {"status": "updated", "source": source},
    )

    main.main()

    assert "dbip-city-lite" in capsys.readouterr().out


def test_cli_update_prefix_source_does_not_load_prefix_snapshots(monkeypatch, capsys):
    import main

    def fail_load(_data_dir):
        raise AssertionError("CLI update should not preload prefix snapshots")

    monkeypatch.setattr(sys, "argv", ["ipatlas", "update", "cloud-cloudflare"])
    monkeypatch.setattr("main.load_prefix_snapshots", fail_load, raising=False)
    monkeypatch.setattr(
        "main.update_source_from_local_file",
        lambda _repo, source: {"status": "updated", "source": source},
    )

    main.main()

    assert "cloud-cloudflare" in capsys.readouterr().out
