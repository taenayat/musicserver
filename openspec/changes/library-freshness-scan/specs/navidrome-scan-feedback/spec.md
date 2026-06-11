## ADDED Requirements

### Requirement: Admin scan trigger reports its outcome

An admin-triggered Navidrome scan SHALL report whether Navidrome accepted the request, rather than always reporting success. When the scan call fails (Navidrome unreachable or returns an error), the admin endpoint SHALL surface that failure.

#### Scenario: Scan accepted
- **WHEN** an admin triggers a scan and Navidrome accepts it
- **THEN** the endpoint responds with a success outcome
- **AND** the UI confirms the scan was triggered

#### Scenario: Scan rejected or Navidrome unreachable
- **WHEN** an admin triggers a scan and Navidrome is unreachable or returns an error
- **THEN** the endpoint responds with a failure outcome
- **AND** the UI shows that the scan could not be triggered

### Requirement: Scan status visible to admin

The admin UI SHALL show Navidrome scan status — whether a scan is currently running and when the last scan completed — so an admin can confirm a triggered scan actually ran.

#### Scenario: Scanning indicator
- **WHEN** Navidrome is mid-scan
- **THEN** the admin UI indicates scanning is in progress

#### Scenario: Last scan time shown
- **WHEN** a scan has completed
- **THEN** the admin UI shows how long ago the last scan finished
