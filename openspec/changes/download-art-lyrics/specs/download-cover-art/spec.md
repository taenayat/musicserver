## ADDED Requirements

### Requirement: Downloads carry embedded cover art

Every successfully downloaded track SHALL have cover art embedded in the audio file so Navidrome and Symfonium display it.

- For YouTube downloads, the system SHALL embed the video/track thumbnail into the output file.
- For Deezer (deemix) downloads, the system SHALL ensure deemix's artwork output is enabled so finished files contain embedded art (and/or a folder cover image Navidrome can read).

#### Scenario: YouTube download has art
- **WHEN** a YouTube track finishes downloading
- **THEN** the resulting audio file contains an embedded cover image

#### Scenario: Deezer download has art
- **WHEN** a Deezer track finishes downloading
- **THEN** the resulting audio file contains embedded cover art (or a folder cover image is present)

### Requirement: Backfill missing cover art for existing files

An admin SHALL be able to trigger a backfill that scans the library for tracks lacking embedded art (and lacking a folder cover) and adds art to them. For tracks with a known Deezer id, the canonical Deezer cover SHALL be used as the source. After the backfill the system SHALL trigger a Navidrome scan.

#### Scenario: Backfill adds art to a bare file
- **WHEN** an admin triggers the cover-art backfill and a library track has no embedded art
- **THEN** the system fetches a cover (Deezer cover when a Deezer id is known) and embeds it
- **AND** a Navidrome scan is triggered afterward

#### Scenario: Backfill skips files that already have art
- **WHEN** the backfill encounters a track that already has embedded or folder art
- **THEN** it leaves that track unchanged

#### Scenario: Backfill reports results
- **WHEN** the backfill completes
- **THEN** the system reports how many files were updated
