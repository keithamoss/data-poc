"""The scenario map's vocabulary (REQ-GEN-386 criterion 4): what a scenario's
link lands on, named semantically (REQ-DASH-208 criterion 2). The generator
writes these names into its placements and the map writer reads them back;
the dashboard owns the mapping from each name to its element.
"""
#: WHAT A SCENARIO'S LINK LANDS ON (REQ-DASH-208 criterion 2) - named
#: semantically, never by a CSS selector or a pixel offset: the page owns the
#: mapping from each name to its element, so a restyle moves nothing here.
AS_AT_PANEL = "as-at-panel"
VERDICT_LINE = "verdict-line"
SUBSTITUTION_DRILL_DOWN = "substitution-drill-down"
STANDING_IN_PILL = "standing-in-pill"
SUPPLY_HISTORY_ROW = "supply-history-row"
#: A period's composition view (REQ-DASH-209 criterion 7) - TS-55's.
PERIOD_COMPOSITION = "period-composition"
SUBJECTS = (AS_AT_PANEL, VERDICT_LINE, SUBSTITUTION_DRILL_DOWN, STANDING_IN_PILL,
            PERIOD_COMPOSITION,
            SUPPLY_HISTORY_ROW)
