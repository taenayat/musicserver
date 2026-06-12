## ADDED Requirements

### Requirement: Telegram is canonical; additions flow to the SSD automatically

Reconciliation SHALL treat the channel as the source of truth. Audio present in the channel but absent from the SSD/library SHALL be downloaded into `/music`, indexed into the library, marked Telegram-backed, and made visible to Navidrome via a scan. Such additions SHALL be applied automatically and SHALL NOT be surfaced as discrepancies.

#### Scenario: New channel track is imported
- **WHEN** the channel contains an audio file with no matching library track
- **THEN** reconciliation downloads it into `/music`, indexes it, and triggers a Navidrome scan

#### Scenario: Already-present track is skipped
- **WHEN** a channel track already matches a library track (by recorded id, fingerprint, or filename)
- **THEN** reconciliation does not re-import it

### Requirement: SSD-only tracks are detected as deletion candidates

Reconciliation SHALL identify library/SSD tracks that are recorded as Telegram-backed but whose backing message no longer exists in the channel, and SHALL present them as deletion candidates rather than deleting them automatically.

#### Scenario: Track removed from channel becomes a candidate
- **WHEN** a previously-backed track's message is no longer in the channel
- **THEN** the track is listed as an SSD-only deletion candidate

#### Scenario: Additions are not listed as candidates
- **WHEN** reconciliation finds channel additions
- **THEN** they are imported and never appear in the deletion-candidate list

### Requirement: Reconciliation is safe against bad listings

Reconciliation SHALL NOT produce deletion candidates from an empty or failed channel listing. A fetch error or an empty result SHALL abort the run without flagging any track for deletion.

#### Scenario: Failed fetch aborts safely
- **WHEN** the channel listing fails or returns empty unexpectedly
- **THEN** reconciliation aborts and no deletion candidates are produced
- **AND** the error is logged
