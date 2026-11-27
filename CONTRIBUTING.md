# Contributing to AlgoRE

Thanks for helping improve an independent, clean-room research project.

## Ground rules

- Keep claims honest. Mark anything not publicly verifiable as `inferred` or a clean-room design; never present a guess as a confirmed fact.
- No real credentials, live endpoints, customer data, or generated secrets in commits. Use `*.example` files with placeholders.
- Research software only: no advice to deploy capital, and no claims of guaranteed returns.

## Development

```bash
# Engine
cd engine && python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt && pytest -v

# Dashboard
cd dashboard && npm install
NODE_OPTIONS="--max-old-space-size=2048" npm run lint
NODE_OPTIONS="--max-old-space-size=2048" npm run build
```

CI runs both suites on every push and pull request. Keep them green.

## Pull requests

1. Open an issue first for substantial changes so the design can be discussed.
2. One concern per PR, with a short description of the problem and the verification you ran.
3. Add or update tests for behaviour changes. Include exact pass/fail counts in the PR description.
4. Keep the UI mobile-first: 390 px width, 44 px minimum tap targets, no horizontal scrolling.

## Reporting security issues

Do not open a public issue for a credential leak or exploitable vulnerability. Use GitHub's private security reporting for this repository, or contact the maintainer directly. Include impact and reproduction steps, not live secrets.

By contributing you agree that your work is licensed under the MIT License.
