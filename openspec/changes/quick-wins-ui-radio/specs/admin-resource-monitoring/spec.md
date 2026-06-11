## ADDED Requirements

### Requirement: Admin overview shows RAM usage history

The admin overview SHALL display a RAM usage sparkline alongside the existing CPU sparkline, sourced from the metrics history already collected by the gateway. The current RAM figure SHALL continue to be shown as a numeric row.

#### Scenario: RAM sparkline renders
- **WHEN** an admin opens the overview and metrics history has more than one point
- **THEN** a RAM sparkline is shown next to the CPU sparkline
- **AND** it plots the collected RAM-per-sample values

#### Scenario: Insufficient history
- **WHEN** fewer than two metrics points exist
- **THEN** the RAM sparkline is omitted, matching the CPU sparkline's behavior
