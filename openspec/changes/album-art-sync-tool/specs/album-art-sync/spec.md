## ADDED Requirements

### Requirement: Scan the library for tracks missing cover art

An admin SHALL be able to trigger a scan that identifies library tracks with no cover art — defined as no embedded image in the audio file and no folder cover image (`cover.*`/`folder.*`/`front.*`) in the track's directory. The scan SHALL return the list of such tracks with enough metadata to display them (title, artist, album, file path) and, where a replacement is available, a proposed cover image URL.

#### Scenario: Scan returns only missing-art tracks
- **WHEN** an admin runs the album-art sync scan
- **THEN** the result lists tracks that have neither embedded art nor a folder cover
- **AND** tracks that already have art are not listed

#### Scenario: Proposed cover shown when available
- **WHEN** a listed track has a known Deezer id
- **THEN** the result includes a proposed Deezer cover URL for it

#### Scenario: Track with no cover source
- **WHEN** a listed track has no known Deezer id and no other cover source
- **THEN** it is marked as having no available replacement and cannot be applied

### Requirement: Select and apply art to chosen tracks

The admin SHALL be able to select individual tracks from the scan results or use a "select all" control, and apply art to the selected, fixable tracks in a single action. Applying SHALL embed the proposed cover into each selected track's file and SHALL trigger a Navidrome scan afterward. Tracks with no available replacement SHALL be excluded from the apply.

#### Scenario: Apply to a selected subset
- **WHEN** an admin selects some tracks and applies
- **THEN** the system embeds art into only those tracks
- **AND** triggers a Navidrome scan
- **AND** reports how many tracks were updated

#### Scenario: Select all then apply
- **WHEN** an admin uses "select all" and applies
- **THEN** every fixable listed track receives embedded art
- **AND** un-fixable tracks (no replacement) are skipped

#### Scenario: Result reflects applied art
- **WHEN** the apply completes and the scan is re-run
- **THEN** the updated tracks no longer appear in the missing-art list
