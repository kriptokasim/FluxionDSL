# Fluxion DSL v2

Fluxion is a minimalist domain-specific language for security automation. This
repository contains the parser, runtime, and sample playbooks for HTTP probing
and SSRF/OAST beaconing.

## Getting Started

```bash
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
PYTHONPATH=. .venv/bin/python -m pytest
```

## Real SSRF/OAST Examples

Use the Interactsh helpers in `examples/ssrf_interactsh_single.flx` and
`examples/ssrf_interactsh_spray.flx` to emit beacons against
`d41r8ucgtqkrv6t72u0gmht8euiepuo44.oast.live`:

```bash
FLUXION_STDLIB=requests PYTHONPATH=. \
  .venv/bin/python -m fluxion -s examples/ssrf_interactsh_single.flx -D token=mytoken
```

> **Note:** If the environment blocks outbound DNS/HTTP, the scripts will report
> `NameResolutionError`. Run them from a networked host to observe callbacks in
> Interactsh.

## Repository Layout

- `fluxion/` – CLI entrypoint, parser, runtime
- `examples/` – Fluxion playbooks, including SSRF/OAST demos
- `tests/` – Pytest regression suite

## Contributing

1. Fork the repository and create a feature branch.
2. Add tests alongside code changes.
3. Run `pytest` before opening a pull request.

## License

Add your preferred license text in a `LICENSE` file.
