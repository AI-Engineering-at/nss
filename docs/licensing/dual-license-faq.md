# NSS v3.1.1 -- Dual-License FAQ

[Back to Main Documentation](../README.md) | [Full White Paper](../white-paper/NSS-v3.1.1-Enterprise-White-Paper.md)

---

## Overview

NSS v3.1.1 uses a dual-license model: AGPL-3.0-or-later for open-source use and a commercial license for proprietary/closed-source deployments. This FAQ answers the most common licensing questions.

---

## Frequently Asked Questions

### What is the AGPL-3.0-or-later license?

The GNU Affero General Public License v3.0 or later (AGPL-3.0-or-later) is a copyleft open-source license. It grants you the freedom to use, modify, and distribute the software, with the condition that any modified versions -- including those accessed over a network (e.g., as a web service) -- must also be released under AGPL terms with full source code.

### Who can use NSS for free under AGPL-3.0-or-later?

The AGPL-3.0-or-later license allows free use for:

- **Individuals** -- unlimited personal use
- **Open-source projects** -- must be GPL-compatible
- **Research and academia** -- educational and research purposes
- **Non-profit organizations** -- organizational use

**Conditions:** You must make your source code available if you distribute or provide network access to a modified version of NSS.

### When do I need a commercial license?

You need a commercial license if:

- Your company uses NSS in **closed-source software**
- You operate NSS as part of a **SaaS product** and do not want to open-source your code
- You embed NSS in **proprietary embedded systems**
- You cannot or do not want to comply with AGPL-3.0-or-later source code disclosure requirements

### What are the commercial license pricing tiers?

| Tier | Company Size | Annual License | Support Level | SLA |
|---|---|---|---|---|
| **Startup** | < 50 employees | 5,000 EUR | 8x5 Email | 99.5% |
| **SMB** | 50--500 employees | 25,000 EUR | 24x7 Phone | 99.9% |
| **Enterprise** | > 500 employees | Custom pricing | 24x7 Dedicated | 99.95% |

### What about NSS dependencies? Are there additional license costs?

No. All NSS dependencies use permissive or compatible open-source licenses:

| Dependency | License |
|---|---|
| Mistral AI | Apache 2.0 |
| Qdrant | AGPL-3.0 (compatible) |
| Redis | BSD 3-Clause |
| Ollama | MIT |
| all-MiniLM-L6-v2 | Apache 2.0 |
| OPA (Open Policy Agent) | Apache 2.0 |

There are no license conflicts and no additional licensing costs for dependencies.

### Can I use NSS in my SaaS product?

**Under AGPL-3.0-or-later:** Yes, but you must release the source code of your entire application (including modifications to NSS) under AGPL terms. This means your SaaS product's code would need to be open-sourced.

**Under the commercial license:** Yes, without any source code disclosure requirement. This is the recommended option for SaaS companies that want to keep their code proprietary.

### What does the commercial license include beyond the license grant?

Depending on your tier, the commercial license includes:

- **Support:** Email (Startup), 24x7 phone (SMB), or dedicated support engineer (Enterprise)
- **SLA guarantees:** 99.5% to 99.95% uptime
- **Response time:** Under 1 hour for Enterprise tier
- **No AGPL obligations:** No source code disclosure required

### What is the ROI of the commercial license?

For an enterprise with 1M requests/month:

| Metric | Value |
|---|---|
| NSS License (SMB tier) | 25,000 EUR/year |
| API cost savings vs. OpenAI | ~4,000 EUR/year |
| Break-even | ~6.25 years |
| 10-year TCO (NSS) | ~45,000 EUR |
| 10-year TCO (OpenAI equivalent) | ~146,000 EUR |
| **10-year savings** | **~101,000 EUR** |

Note: The ROI calculation includes the full GDPR compliance, Cloud Act risk elimination, and enterprise security features that would require significant additional investment with alternative solutions.

### Can I contribute back to NSS under the commercial license?

Yes. Contributions are welcome regardless of your license type. Contributions to the open-source repository are made under AGPL-3.0-or-later terms, following the project's contribution guidelines.

### How do I obtain a commercial license?

Contact the NSS team:
- **Email:** support@nss-standard.eu
- **GitHub:** https://github.com/LEEI1337/NSS

---

## References

- [GDPR Compliance Matrix](../compliance/gdpr-matrix.md)
- [Scaling Guide](../deployment/scaling-guide.md)
- [Full White Paper](../white-paper/NSS-v3.1.1-Enterprise-White-Paper.md)
