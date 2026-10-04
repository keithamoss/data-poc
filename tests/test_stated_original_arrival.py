"""A supply received by hand records when it was ORIGINALLY received, as a
person's statement beside the receipt (REQ-PIPE-103 criteria 9-20), and
every delivery records whether a person filed it, how and who
(REQ-PIPE-147)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from qa_tools.common import delivery, delivery_log, hand_filing, supply_db

PERTH = timezone(timedelta(hours=8))
NOW = datetime(2026, 9, 25, 9, 0, tzinfo=PERTH)


class TestResolvingTheAnswer:
    """Criteria 13, 15, 16, 17 and 20 - pure, before anything is filed."""

    FILES = ["a.csv", "b.csv"]

    def test_not_known_is_recorded_as_such_for_every_file(self):
        got = hand_filing.resolve_original("not known", files=self.FILES, received_at=NOW)
        assert got == {"a.csv": delivery.NOT_KNOWN, "b.csv": delivery.NOT_KNOWN}

    def test_a_time_with_an_offset_is_kept_with_it(self):
        got = hand_filing.resolve_original("2026-09-20T10:00:00+00:00",
                                           files=self.FILES, received_at=NOW)
        assert got["a.csv"] == "2026-09-20T10:00:00+00:00"

    def test_a_naive_time_is_read_on_the_assets_own_clock(self):
        """Criterion 16."""
        got = hand_filing.resolve_original("2026-09-20 14:30", files=["a.csv"],
                                           received_at=NOW)
        assert got["a.csv"] == "2026-09-20T14:30:00+08:00"

    def test_a_time_after_our_receipt_is_refused(self):
        """Criterion 15."""
        with pytest.raises(hand_filing.CannotFile, match="later than"):
            hand_filing.resolve_original("2026-09-26T09:00:00+08:00", files=["a.csv"],
                                         received_at=NOW)

    def test_storage_takes_each_objects_own_time(self):
        """Criteria 17 and 20."""
        times = {"a.csv": datetime(2026, 9, 1, 1, tzinfo=timezone.utc),
                 "b.csv": datetime(2026, 9, 2, 1, tzinfo=timezone.utc)}
        got = hand_filing.resolve_original("storage", files=self.FILES, received_at=NOW,
                                           storage_times=times)
        assert got == {"a.csv": "2026-09-01T01:00:00+00:00",
                       "b.csv": "2026-09-02T01:00:00+00:00"}

    def test_storage_is_refused_for_a_supply_not_from_s3(self):
        """Criterion 20."""
        with pytest.raises(hand_filing.CannotFile, match="S3"):
            hand_filing.resolve_original("storage", files=["a.csv"], received_at=NOW)

    def test_nonsense_is_refused_rather_than_recorded(self):
        with pytest.raises(hand_filing.CannotFile):
            hand_filing.resolve_original("last tuesday", files=["a.csv"], received_at=NOW)


@pytest.fixture
def tree(tmp_path, private_supply_dsn):
    return tmp_path / "deliveries", tmp_path / "receipts"


def _csv(tmp_path):
    from qa_tools.common import schedule as schedule_mod

    day = schedule_mod.calendar("daily").current.effective_from + timedelta(days=3)
    path = tmp_path / f"birth_registrations_{day.isoformat()}.csv"
    path.write_text("a\n1\n")
    return path


class TestWhatAKeptSupplyRecords:

    def test_the_statement_sits_beside_the_receipt_and_never_replaces_it(self, tmp_path, tree):
        """Criteria 10 and 11: the receipt is still the moment the command
        ran; the statement is its own field, marked as a person's."""
        deliveries, receipts = tree
        filed = hand_filing.file_supply(
            [_csv(tmp_path)], "civil-registration", "run_", received_at=NOW,
            stated_original={"*": "2026-09-20T10:00:00+08:00"}, route="file",
            filed_by="analyst@example.org",
            deliveries_dir=deliveries, receipts_dir=receipts)
        d = delivery.read_delivery(filed.delivery_name, deliveries, receipts)
        (name,) = d.files
        assert d.received_at == NOW, "the receipt is the command's own instant"
        assert d.stated_original == {name: "2026-09-20T10:00:00+08:00"}
        import json
        raw = json.loads((receipts / filed.delivery_name / f"{name}.json").read_text())
        assert raw["originally_received"] == {"value": "2026-09-20T10:00:00+08:00",
                                              "stated_by": "person"}
        assert raw["received_at"] != raw["originally_received"]["value"]

    def test_who_filed_it_is_data_on_the_record(self, tmp_path, tree):
        """REQ-PIPE-147 criteria 1-3 and 6, in both places."""
        deliveries, receipts = tree
        filed = hand_filing.file_supply(
            [_csv(tmp_path)], "civil-registration", "run_", received_at=NOW,
            stated_original={"*": delivery.NOT_KNOWN}, route="file",
            filed_by="analyst@example.org",
            deliveries_dir=deliveries, receipts_dir=receipts)
        d = delivery.read_delivery(filed.delivery_name, deliveries, receipts)
        assert d.filed_by == {"kind": "person", "route": "file", "who": "analyst@example.org"}
        with supply_db.connect(label="test-stated") as conn:
            (record,) = [r for r in delivery_log.records(conn)
                         if r["delivery"] == filed.delivery_name]
            assert record["filed_by"] == d.filed_by
            assert record["files"][0]["originally_received_stated"] == delivery.NOT_KNOWN

    def test_an_automated_delivery_records_no_person_and_never_asked(self, tmp_path, tree):
        """REQ-PIPE-147 criterion 5, REQ-PIPE-103 criterion 18."""
        deliveries, receipts = tree
        delivery.write_delivery("auto", {"x.csv": "a\n1\n"}, received_at=NOW,
                                deliveries_dir=deliveries, receipts_dir=receipts)
        d = delivery.read_delivery("auto", deliveries, receipts)
        assert d.filed_by == {"kind": "automated"} and d.stated_original == {}

    def test_a_route_outside_the_four_is_refused(self, tmp_path, tree):
        deliveries, receipts = tree
        with pytest.raises(delivery.DeliveryFormatError):
            hand_filing.file_supply([_csv(tmp_path)], "civil-registration", "run_",
                                    received_at=NOW, stated_original={"*": "not-known"},
                                    route="email", filed_by="a@b.c",
                                    deliveries_dir=deliveries, receipts_dir=receipts)

    def test_nothing_is_filed_without_a_statement_or_without_who(self, tmp_path, tree):
        """REQ-PIPE-103 criterion 13 (an answer is required) and REQ-PIPE-147
        criterion 4 (an identity is required)."""
        deliveries, receipts = tree
        with pytest.raises(hand_filing.CannotFile):
            hand_filing.file_supply([_csv(tmp_path)], "civil-registration", "run_",
                                    received_at=NOW, stated_original=None, route="file",
                                    filed_by="a@b.c",
                                    deliveries_dir=deliveries, receipts_dir=receipts)
        with pytest.raises(hand_filing.CannotFile, match="who"):
            hand_filing.file_supply([_csv(tmp_path)], "civil-registration", "run_",
                                    received_at=NOW, stated_original={"*": "not-known"},
                                    route="file", filed_by="",
                                    deliveries_dir=deliveries, receipts_dir=receipts)
        assert not deliveries.exists() or not any(deliveries.iterdir())


class TestTheCommandLine:

    def test_a_script_keeping_a_supply_must_say_when_it_originally_arrived(
            self, tmp_path, monkeypatch, private_supply_dsn):
        """Criterion 14: no terminal and no --originally-received - refused,
        the missing flag named, nothing filed."""
        import click
        from cli import common
        from qa_tools.common import git_identity

        monkeypatch.setattr(git_identity, "get_run_by", lambda: "a@b.c")
        monkeypatch.setattr(delivery, "DELIVERIES_DIR", tmp_path / "deliveries")
        monkeypatch.setattr(delivery, "RECEIPTS_DIR", tmp_path / "receipts")
        with pytest.raises(click.ClickException) as caught:
            common.file_or_trial([str(_csv(tmp_path))], "civil-registration", "run_",
                                 keep=True, route="file")
        assert "--originally-received" in caught.value.message
        assert not (tmp_path / "deliveries").exists()

    def test_nobody_to_name_means_nothing_filed(self, tmp_path, monkeypatch, private_supply_dsn):
        """REQ-PIPE-147 criterion 4."""
        import click
        from cli import common
        from qa_tools.common import git_identity

        def _none():
            raise git_identity.MissingGitIdentityError("no user.email")
        monkeypatch.setattr(git_identity, "get_run_by", _none)
        monkeypatch.setattr(delivery, "DELIVERIES_DIR", tmp_path / "deliveries")
        with pytest.raises(click.ClickException) as caught:
            common.file_or_trial([str(_csv(tmp_path))], "civil-registration", "run_",
                                 keep=True, route="file", originally="not-known")
        assert "git config user.email" in caught.value.message
        assert not (tmp_path / "deliveries").exists()

    def test_the_closing_message_sets_the_statement_beside_the_receipt(self):
        """Criterion 19 - labelled as the filer's statement, never as the
        receipt."""
        from cli import common

        text = common.describe_original({"a.csv": "2026-09-20T10:00:00+08:00"}, NOW)
        assert "Received by us" in text and "stated by you" in text
        assert common.describe_original({"a.csv": delivery.NOT_KNOWN}, NOW).count("not known") == 1


class TestItIsShownBesideTheReceipt:
    """REQ-PIPE-103 criterion 19 and REQ-PIPE-147 criterion 7 - every place
    a delivery is shown, asserted at the last transform before a reader."""

    def _kept(self, tmp_path, tree):
        deliveries, receipts = tree
        filed = hand_filing.file_supply(
            [_csv(tmp_path)], "civil-registration", "run_", received_at=NOW,
            stated_original={"*": "2026-09-20T10:00:00+08:00"}, route="file",
            filed_by="keith@example.org", deliveries_dir=deliveries, receipts_dir=receipts)
        from qa_tools.common import arrivals, filing
        found = [a for a in arrivals.arrivals_for("civil-registration", "run_",
                                                  deliveries, receipts)
                 if a.delivery_name == filed.delivery_name]
        filing.file_arrivals(found)
        return filed, found[0]

    def test_the_dashboards_arrival_block_carries_both(self, tmp_path, tree):
        from pipeline import recorded_arrival

        _filed, arrival = self._kept(tmp_path, tree)
        block = recorded_arrival.for_run("birth-registrations", arrival.received_at)
        assert block["arrivedAt"] is not None
        assert block["statedOriginal"] == "2026-09-20T10:00:00+08:00"
        assert block["statedOriginal"] != block["arrivedAt"]
        assert block["filedBy"]["kind"] == "person" and block["filedBy"]["route"] == "file"

    def test_the_person_is_resolved_through_people_yaml(self, monkeypatch):
        from qa_tools.common import people

        cfg = {"people": {"keith@example.org": {"name": "Keith Moss"}}}
        assert people.display_name("keith@example.org", cfg) == "Keith Moss"
        assert people.display_name("stranger@example.org", cfg) == "stranger@example.org"

    def test_mothman_supply_deliveries_says_who_and_when_stated(
            self, tmp_path, tree, monkeypatch):
        from click.testing import CliRunner
        from cli.supply import supply_group

        filed, _ = self._kept(tmp_path, tree)
        deliveries, receipts = tree
        monkeypatch.setattr(delivery, "DELIVERIES_DIR", deliveries)
        monkeypatch.setattr(delivery, "RECEIPTS_DIR", receipts)
        out = CliRunner().invoke(supply_group, ["deliveries", "--name", filed.delivery_name],
                                 terminal_width=200).output
        flat = " ".join(out.split())
        assert "by hand (file)" in flat
        assert "originally received" in flat and "stated by the person" in flat

    def test_an_automated_delivery_says_so(self, tmp_path, tree, monkeypatch):
        from click.testing import CliRunner
        from cli.supply import supply_group

        deliveries, receipts = tree
        delivery.write_delivery("auto", {"x.csv": "a\n1\n"}, received_at=NOW,
                                deliveries_dir=deliveries, receipts_dir=receipts)
        monkeypatch.setattr(delivery, "DELIVERIES_DIR", deliveries)
        monkeypatch.setattr(delivery, "RECEIPTS_DIR", receipts)
        out = CliRunner().invoke(supply_group, ["deliveries"], terminal_width=200).output
        assert "automatically" in out


class TestTheS3Offer:
    """Criterion 17: each object's own LastModified shown together as one
    set and confirmed in ONE step - or one answer for every file instead."""

    def _tty(self, monkeypatch):
        from cli import common
        monkeypatch.setattr(common.sys.stdin, "isatty", lambda: True)
        monkeypatch.setattr(common.sys.stdout, "isatty", lambda: True)
        return common

    def test_confirming_the_set_takes_each_objects_own_time(self, monkeypatch):
        common = self._tty(monkeypatch)
        asked = []
        monkeypatch.setattr(common, "confirm", lambda *a, **k: asked.append(a) or True)
        times = {"a.csv": datetime(2026, 9, 1, 1, tzinfo=timezone.utc),
                 "b.csv": datetime(2026, 9, 2, 1, tzinfo=timezone.utc)}
        assert common._ask_original(["a.csv", "b.csv"], times) == hand_filing.STORAGE
        assert len(asked) == 1, "one step for the whole set, never one per object"

    def test_declining_asks_once_for_one_answer(self, monkeypatch):
        import click
        common = self._tty(monkeypatch)
        monkeypatch.setattr(common, "confirm", lambda *a, **k: False)
        monkeypatch.setattr(click, "prompt", lambda *a, **k: "not known")
        times = {"a.csv": datetime(2026, 9, 1, 1, tzinfo=timezone.utc)}
        assert common._ask_original(["a.csv"], times) == "not known"
