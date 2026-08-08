# Security policy

## Supported version

ReefProof is pre-1.0 software. Security fixes are made on the latest `0.1.x`
release line and the default branch; older development snapshots are not
supported.

## Reporting a vulnerability

Do not open a public issue for a suspected vulnerability or include secrets,
private aquarium configuration, device identifiers, database files, or browser
evidence in a report. Use GitHub's private vulnerability-reporting feature for
this repository. If that feature is unavailable, open a public issue containing
only a request for a private security contact and no vulnerability details.

Reports should describe the affected version, impact, reproduction boundary,
and whether any living-system or credential exposure may have occurred. Never
test against another person's system or a living HYDROS controller.

## Security boundary

HYDROS remains runtime authority. ReefProof v0.1 has no live HYDROS transport,
MQTT publication, equipment control, or automatic remediation. A vulnerability
that could cross this boundary is release-blocking.
