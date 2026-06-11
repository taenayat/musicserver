## ADDED Requirements

### Requirement: Content changes trigger an accepted Navidrome scan

Whenever the gateway changes library content on disk — a completed download, a radio like, a radio dismiss/cleanup, a recall, or a backfill — it SHALL trigger a Navidrome scan, and a failure to reach Navidrome SHALL be logged rather than silently lost.

#### Scenario: Download triggers scan
- **WHEN** a permanent download completes
- **THEN** the gateway triggers a Navidrome scan
- **AND** any failure to reach Navidrome is logged

#### Scenario: Radio like triggers scan
- **WHEN** a user likes a radio track (moving it into the permanent library)
- **THEN** the gateway triggers a Navidrome scan

### Requirement: Symfonium freshness is documented

Because Subsonic provides no server-to-client push, the system SHALL document how to make new music appear in Symfonium without manual refresh — specifically the Symfonium background library-sync setting and a recommended interval — and the admin UI SHALL set the expectation that the gateway keeps Navidrome current but the client controls its own refresh cadence.

#### Scenario: Guidance available
- **WHEN** a user wants new downloads to appear automatically in Symfonium
- **THEN** documentation explains enabling Symfonium's background sync and a recommended interval

#### Scenario: Admin UI expectation
- **WHEN** an admin views the scan controls
- **THEN** helper text clarifies that the gateway updates Navidrome and Symfonium refreshes on its own sync schedule
