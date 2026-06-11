## ADDED Requirements

### Requirement: Radio seed picker keeps its search field pinned

The radio seed picker SHALL keep its search input fixed at the top of the picker while matching results scroll beneath it, so the input does not move as results load or as the on-screen keyboard appears. This SHALL match the behavior of the main Search tab.

#### Scenario: Search field stays in place while typing
- **WHEN** a user types in the radio seed picker and results load
- **THEN** the search input remains fixed at the top of the picker
- **AND** results appear in a scrollable area below it

#### Scenario: Selecting a seed
- **WHEN** a user selects a result from the picker
- **THEN** the seed is chosen and the confirm step is shown, unchanged from current behavior
