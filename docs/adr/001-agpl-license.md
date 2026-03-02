# ADR-001: AGPL-3.0-or-later License Choice

## Status

Accepted

## Context

NSS needs a license that ensures the standard remains open and sovereign while allowing commercial adoption. The license must prevent proprietary forks from undermining European AI sovereignty goals.

## Decision

Use AGPL-3.0-or-later as the primary license with a commercial dual-license option.

## Rationale

- **Copyleft protection**: AGPL ensures modifications to NSS remain open source, preventing vendor lock-in
- **Network use clause**: AGPL Section 13 requires source disclosure for SaaS deployments, critical for AI infrastructure
- **EU alignment**: Strong copyleft aligns with European digital sovereignty goals
- **Commercial viability**: Dual-license model (AGPL-3.0-or-later + Commercial) allows enterprises to use NSS without copyleft obligations via commercial license
- **Community building**: AGPL encourages contribution back to the standard

## Alternatives Considered

- **MIT/Apache-2.0**: Too permissive; allows proprietary forks without contribution
- **GPL-3.0**: No network use clause; SaaS providers could use NSS without sharing modifications
- **BSL (Business Source License)**: Time-delayed open source; conflicts with sovereignty-first goals
- **EUPL**: EU-specific license with limited global adoption and tooling support

## Consequences

- Enterprises must purchase commercial license for proprietary use
- All modifications to NSS core must be shared under AGPL
- Contributors must sign CLA for dual-license compatibility
