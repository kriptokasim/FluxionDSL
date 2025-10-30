# Fluxion DSL - Cybersecurity Scanning Language

## Overview
Fluxion is a Domain-Specific Language (DSL) designed for cybersecurity reconnaissance and vulnerability scanning. It provides a simple, Python-like syntax for writing security testing scripts with built-in HTTP functions, OAST (Out-of-Band Application Security Testing) capabilities, and easy-to-use control flow.

## Current State
- **Version**: 2.2.0
- **Language**: Python 3.11+
- **Status**: Fully functional with complete parser, runtime, and stdlib
- **Purpose**: Security scanning, reconnaissance, SSRF testing, HTTP probing

## Recent Changes
- Fixed grammar to support complete DSL syntax (functions, loops, conditionals, let statements)
- Fixed desugaring bug (extra closing brace)
- Integrated real stdlib with HTTP functions (requests-based)
- Added multiline support for lists and maps
- Added `len()` function for collection size operations
- All core language features working: variables, functions, loops, if/else, return statements

## Project Architecture

### Core Components
1. **Grammar** (`fluxion/grammar/fluxion.lark`)
   - Lark-based parser grammar
   - Supports Python-like syntax with security-focused commands
   - Features: let, return, if/else, for loops, functions, expressions, collections

2. **Parser** (`fluxion/core/parser.py`)
   - Desugaring step: transforms `command key=value` → `command { key: value }`
   - Builds AST (Abstract Syntax Tree) from source
   - Transforms parsed tree into Node objects

3. **Runtime** (`fluxion/runtime/runner_v2.py`)
   - Executes AST nodes
   - Manages variable scopes
   - Function invocation and standard library integration

4. **Standard Library** (`fluxion/stdlib.py`)
   - `http_get(url)` - HTTP GET requests with full response data
   - `http_head(url)` - HTTP HEAD requests for headers only
   - `sleep(seconds)` - Delay execution
   - `join(a, b)` - String concatenation
   - `oast_http_ping(host, token)` - OAST HTTP pinging
   - `jsonify(obj)` - Convert objects to JSON strings
   - `len(collection)` - Get length of lists/strings

## Language Features

### Variables and Assignments
```fluxion
let target = "https://example.com"
let ports = [80, 443, 8080]
```

### Functions
```fluxion
func scan_port(host, port) {
  let url = join("http://", host, ":", port)
  let response = http_head(url)
  return response
}

let result = scan_port("example.com", "80")
```

### Control Flow
```fluxion
# If/else conditionals
if (is_vulnerable) {
  echo severity="high", action="alert_team"
} else {
  echo status="safe"
}

# For loops
for target in targets {
  let response = http_get(target)
  echo url=target, status=response.status
}
```

### Commands (Echo)
```fluxion
echo status="scanning", target="example.com"
echo result=some_variable
```

### Operators
- Arithmetic: `+`, `-`, `*`, `/`, `%`
- Comparison: `==`, `!=`, `<`, `>`, `<=`, `>=`
- Logical: `&&`, `||`, `!`
- Nullish coalescing: `??`
- Ternary: `condition ? true_val : false_val`

## Example Scripts

See the `examples/` directory:
- `basic_recon_oast.flx` - Simple echo demo
- `interp_demo.flx` - String interpolation test
- `oast_recon.flx` - OAST reconnaissance
- `ssrf_http_probe.flx` - SSRF vulnerability testing with HTTP probing
- `security_demo.flx` - Comprehensive feature demonstration

## Usage

### Command Line
```bash
# Run a Fluxion script
python -m fluxion -s script.flx

# Pass predefined variables
python -m fluxion -s script.flx -D target=example.com -D debug=true

# Example output (JSON)
{
  "return": <return_value>,
  "vars": {
    "variable_name": "value",
    ...
  }
}
```

### Programmatic Usage
```python
from fluxion.runtime.runner_v2 import RunnerV2

runner = RunnerV2()
result = runner.run_file("script.flx", variables={"target": "example.com"})
print(result)
```

## Testing
```bash
# Run all tests
pytest tests/

# Run specific test
pytest tests/test_runner_smoke.py
```

## Security Use Cases

1. **Reconnaissance**: Gather information about targets
2. **SSRF Testing**: Test for Server-Side Request Forgery vulnerabilities
3. **HTTP Probing**: Check service availability and response headers
4. **OAST**: Out-of-band interaction detection
5. **Batch Scanning**: Process multiple targets efficiently

## User Preferences
- CLI-based security tool (no frontend)
- Focused on cybersecurity/pentesting workflows
- JSON output for easy integration with other tools
