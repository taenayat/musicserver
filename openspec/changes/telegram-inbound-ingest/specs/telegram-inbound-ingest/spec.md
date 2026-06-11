## ADDED Requirements

### Requirement: Import audio posted to the Telegram channel

When Telegram is configured, the gateway SHALL watch its configured channel for incoming audio messages (uploaded or forwarded) and import them into the music library. For each new audio message the system SHALL download the file, place it under `/music/<Artist>/<Album>/` using available metadata, index it into the library, and trigger a Navidrome scan so it becomes playable in Symfonium.

#### Scenario: Forwarded track is imported
- **WHEN** a user forwards an audio message into the configured channel
- **THEN** the gateway downloads the file into the library
- **AND** indexes it and triggers a Navidrome scan
- **AND** the track becomes playable in Symfonium after sync

#### Scenario: Uploaded audio file is imported
- **WHEN** a user uploads an audio file directly to the channel
- **THEN** the gateway imports it the same way

#### Scenario: Non-audio messages ignored
- **WHEN** a non-audio message appears in the channel
- **THEN** the gateway ignores it

### Requirement: Ingest is reliable across restarts and avoids duplicates

The gateway SHALL track the last processed Telegram update so a restart does not reprocess already-imported messages. It SHALL de-duplicate imports against the existing library so a track already present is not imported again, and SHALL mark imported files as Telegram-sourced so they are not redundantly re-uploaded to the channel.

#### Scenario: No reprocessing after restart
- **WHEN** the gateway restarts after importing messages
- **THEN** it resumes from the last processed update and does not re-import prior messages

#### Scenario: Duplicate skipped
- **WHEN** an incoming audio matches a track already in the library
- **THEN** the gateway skips importing it

#### Scenario: Imported file not re-uploaded
- **WHEN** a file imported from Telegram is indexed
- **THEN** it is recorded as already backed by Telegram and is not re-uploaded
