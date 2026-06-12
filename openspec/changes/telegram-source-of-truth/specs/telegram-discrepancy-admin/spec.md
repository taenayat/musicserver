## ADDED Requirements

### Requirement: Admin discrepancy panel for SSD-only tracks

The admin Telegram tab SHALL let an admin run a reconciliation and view the resulting SSD-only deletion candidates (tracks no longer in the channel). For each candidate the panel SHALL show enough metadata to identify it (title, artist, album, file path).

#### Scenario: View discrepancies
- **WHEN** an admin runs reconcile from the Telegram tab
- **THEN** the SSD-only deletion candidates are listed with identifying metadata

#### Scenario: Additions summarized, not listed for action
- **WHEN** reconcile imported channel additions
- **THEN** the panel reports how many were imported but does not require admin action on them

### Requirement: Admin-gated removal of SSD-only tracks

The admin SHALL be able to select individual candidates or use a select-all control and remove the selected tracks from the SSD in one action. Removal SHALL delete the files from `/music`, remove their library rows, and trigger a Navidrome scan. No removal SHALL occur without explicit admin action.

#### Scenario: Remove selected
- **WHEN** an admin selects candidates and confirms removal
- **THEN** only those files are deleted from the SSD and their library rows removed
- **AND** a Navidrome scan is triggered

#### Scenario: Select all then remove
- **WHEN** an admin uses select-all and confirms
- **THEN** every listed candidate is removed

#### Scenario: Nothing removed automatically
- **WHEN** reconcile detects deletion candidates but the admin takes no action
- **THEN** the files remain on the SSD
