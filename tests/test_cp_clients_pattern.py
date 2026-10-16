"""Child Protection's Client Register recognises its file under more than one
name (REQ-PIPE-202 criteria 1, 2 and 11)."""
from __future__ import annotations

import pytest
import yaml

from qa_tools.common import arrival_patterns

ROOT = __import__("pathlib").Path(__file__).resolve().parent.parent


class TestThePattern:

    @pytest.mark.parametrize("name", ["cp_clients.csv", "cp_clients_part2.csv",
                                      "cp_clients_2.csv", "cp_clients_resend.csv"])
    def test_cp_clients_and_every_suffixed_name_match(self, name):
        assert arrival_patterns.dataset_for_filename(name) == "cp-clients"

    @pytest.mark.parametrize("name", ["CLIENTS_EXTRACT_FINAL.csv", "placements (2).csv",
                                      "cp_clientsX.csv", "cp_clients_.csv", "cp_clients.CSV"])
    def test_ts38s_names_and_near_misses_stay_unrecognised(self, name):
        assert arrival_patterns.dataset_for_filename(name) != "cp-clients"

    @pytest.mark.parametrize("name", ["cp_carers_2.csv", "cp_placements_2.csv",
                                      "cp_notifications_2.csv"])
    def test_every_other_pattern_is_unchanged(self, name):
        assert arrival_patterns.dataset_for_filename(name) is None

    def test_the_pattern_and_its_comment_in_the_configuration(self):
        text = (ROOT / "contract" / "data-asset.yaml").read_text()
        doc = yaml.safe_load(text)
        found = [ds for agency in doc["hierarchy"]["agencies"]
                 for col in agency["collections"] for ds in col["datasets"]
                 if ds["id"] == "cp-clients"]
        assert found and found[0]["arrival_pattern"] == r"cp_clients(_[^/]+)?\.csv"
        # CRITERION 11: said beside it, as the synthetic asset's demonstration.
        block = text[text.index("table: cp_clients"):text.index("cp_notifications")]
        assert "demonstrat" in block.lower() and "contest" in block.lower()

    def test_the_odcs_transport_value_is_unchanged(self):
        text = (ROOT / "contract" / "child-protection-family-support" / "child-protection-contract.yaml").read_text()
        assert "cp_clients(_" not in text
