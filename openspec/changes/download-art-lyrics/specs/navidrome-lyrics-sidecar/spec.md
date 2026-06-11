## ADDED Requirements

### Requirement: Synced lyrics written as .lrc sidecars

When synced lyrics are available for a track, the system SHALL write them as a `.lrc` sidecar file next to the audio file (same basename, `.lrc` extension) so Navidrome serves them to Symfonium. Writing the sidecar SHALL NOT modify the audio file itself.

The system SHALL write the sidecar at download time when synced lyrics can be fetched, and SHALL trigger a Navidrome scan so the lyrics become visible.

#### Scenario: Sidecar written on download
- **WHEN** a track finishes downloading and synced lyrics are available
- **THEN** a `<track>.lrc` file is written alongside the audio file
- **AND** a Navidrome scan is triggered so the lyrics appear in Symfonium

#### Scenario: No synced lyrics available
- **WHEN** only plain (unsynced) or no lyrics are available
- **THEN** no `.lrc` sidecar is written and the download still completes

#### Scenario: Sidecar is non-destructive
- **WHEN** a sidecar is written
- **THEN** the original audio file's bytes are unchanged

### Requirement: Backfill lyrics sidecars for existing library

An admin SHALL be able to trigger a backfill that walks the existing library and writes `.lrc` sidecars for tracks that have synced lyrics available and no existing sidecar. After the backfill the system SHALL trigger a Navidrome scan and report how many sidecars were written.

#### Scenario: Backfill writes missing sidecars
- **WHEN** an admin triggers the lyrics backfill
- **THEN** the system writes `.lrc` sidecars for tracks with available synced lyrics and no current sidecar
- **AND** triggers a Navidrome scan and reports the count

#### Scenario: Backfill skips existing sidecars
- **WHEN** a track already has a `.lrc` sidecar
- **THEN** the backfill leaves it unchanged
