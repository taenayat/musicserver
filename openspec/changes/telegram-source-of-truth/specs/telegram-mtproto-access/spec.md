## ADDED Requirements

### Requirement: MTProto user-session access to the channel

The gateway SHALL access the Telegram channel through an MTProto user session (not the Bot API) for source-of-truth operations, so it can list full channel history, download files of any size, and detect deletions. Access SHALL require configured API credentials and a stored user session, and SHALL fail closed (no reconciliation) when they are absent.

#### Scenario: List channel audio
- **WHEN** reconciliation runs with a valid session
- **THEN** the gateway can enumerate all audio messages in the channel with a stable per-file identity

#### Scenario: Download without size cap
- **WHEN** the gateway retrieves a track from the channel
- **THEN** it downloads the full file regardless of size (no 20 MB Bot-API limit)

#### Scenario: Missing credentials
- **WHEN** API credentials or the session string are not configured
- **THEN** source-of-truth features are disabled and the gateway logs a clear message, without crashing

### Requirement: Session secrecy

The user session SHALL be stored outside the repository (under the data volume) and SHALL never be written to logs or API responses.

#### Scenario: Session not leaked
- **WHEN** the gateway logs Telegram activity
- **THEN** the session string is never emitted
