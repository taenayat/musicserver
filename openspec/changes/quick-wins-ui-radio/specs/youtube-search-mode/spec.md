## ADDED Requirements

### Requirement: Search source toggle between Deezer and YouTube

The search interface SHALL provide a source toggle with two states, Deezer and YouTube. The active source determines which provider the current query is sent to and which results are displayed.

When YouTube is the active source, the system SHALL query YouTube Music for the current text and display those results in place of Deezer results. When Deezer is active, the system SHALL behave as the default Deezer search.

The toggle SHALL be operable without first typing a query (toggling source is always allowed), and switching source with text already entered SHALL re-run the search against the newly selected source.

The YouTube source SHALL only be offered when YouTube support is enabled (`health.ytdlp_enabled`).

#### Scenario: Toggle to YouTube swaps results
- **WHEN** a user has Deezer results showing and activates the YouTube source
- **THEN** the system queries YouTube for the same text
- **AND** YouTube results replace the Deezer results in the view

#### Scenario: Toggle is usable before typing
- **WHEN** the search box is empty and the user activates the YouTube source
- **THEN** the toggle changes state without being disabled
- **AND** typing a query then searches YouTube

#### Scenario: Toggle back to Deezer
- **WHEN** the YouTube source is active with results showing and the user activates Deezer
- **THEN** the system queries Deezer for the same text and shows Deezer results

#### Scenario: YouTube disabled
- **WHEN** YouTube support is disabled in health flags
- **THEN** the source toggle does not offer a YouTube option
