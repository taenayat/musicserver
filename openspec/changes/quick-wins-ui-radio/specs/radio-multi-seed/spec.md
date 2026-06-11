## ADDED Requirements

### Requirement: Radio stations from track, album, or artist seeds

The system SHALL start a radio station from any of three seed types — track, album, or artist — and SHALL populate the station with related tracks for each.

Because the Deezer public API exposes related tracks only for artists (`/artist/{id}/radio`), the system SHALL resolve a non-artist seed to an artist before fetching related tracks:
- For a track seed, resolve the track's primary artist and use artist radio.
- For an album seed, resolve the album's primary artist and use artist radio.

The system SHALL continue to dedupe results and skip tracks already in the library, returning up to the configured track count.

#### Scenario: Track seed produces a station
- **WHEN** a user starts radio with `seed_type=track`
- **THEN** the system resolves the track's artist and returns related tracks
- **AND** the station is created with at least one track (when the artist has related tracks)

#### Scenario: Album seed produces a station
- **WHEN** a user starts radio with `seed_type=album`
- **THEN** the system resolves the album's artist and returns related tracks
- **AND** the station is created with at least one track (when the artist has related tracks)

#### Scenario: Artist seed still works
- **WHEN** a user starts radio with `seed_type=artist`
- **THEN** the system returns related tracks via artist radio as before

#### Scenario: Seed with no resolvable related tracks
- **WHEN** a seed cannot be resolved to an artist or the artist has no related tracks
- **THEN** the system returns a clear "no radio tracks found" error instead of silently creating an empty station
