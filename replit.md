# Fluxion DSL

## Overview
Fluxion is a Domain-Specific Language (DSL) designed for cybersecurity purposes. It provides a specialized syntax for writing security scanning and reconnaissance scripts.

## Project Type
Command-line tool (CLI) - no web server or frontend

## Current State
The project is fully functional and ready to use. The parser and runtime have been configured to work in the Replit environment.

## Quick Start

Run Fluxion scripts using the command:
```bash
python -m fluxion -s <script.flx>
```

Example with the demo script:
```bash
python -m fluxion -s demo.flx
```

You can also define variables:
```bash
python -m fluxion -s script.flx -D variable_name=value
```

## Project Structure

- `fluxion/` - Main package directory
  - `core/parser.py` - Parser implementation with desugaring logic
  - `grammar/fluxion.lark` - Lark grammar definition
  - `runtime/runner_v2.py` - Runtime execution engine
  - `cli.py` - Command-line interface
  - `stdlib.py` - Standard library functions

- `examples/` - Example Fluxion scripts
  - `basic_recon_oast.flx` - Basic reconnaissance example
  - `ssrf_http_probe.flx` - SSRF scanning example
  - And more...

- `tests/` - Unit tests
- `demo.flx` - Simple demo script

## Fluxion Syntax

### Basic Commands
```
echo message="Hello World"
echo status="ready", tool="scanner"
```

### Variables
```
let x = 3
let name = "test"
let items = [1, 2, 3]
```

### Functions
```
func increment(a) { return a + 1 }
let result = increment(5)
```

### Control Flow
```
if (condition) {
  echo message="true branch"
} else {
  echo message="false branch"
}

for item in items {
  echo value=item
}
```

### Standard Library
- `jsonify()` - Convert objects to JSON
- `join()` - Join strings
- `http_get()` - HTTP GET request
- `http_head()` - HTTP HEAD request

## Dependencies
- lark - Parser generator
- requests - HTTP library
- PyYAML - YAML parser
- rich - Terminal formatting
- pytest - Testing framework

## Recent Changes (Oct 30, 2025)
- Fixed grammar file to support full DSL syntax (functions, loops, conditionals)
- Fixed desugar function brace escaping bug
- Successfully configured and tested in Replit environment
- Added workflow for running demo scripts

## Notes
This is a cybersecurity-focused DSL tool. Use it responsibly and only on systems you have permission to test.
