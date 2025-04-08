# XDDos

**XDDos** is an educational Python-based network DDos tool designed to simulate high traffic on a given server. It is intended for learning purposes only — to understand how networks handle concurrent connections and how server-side protections can be improved.

⚠️ **Disclaimer:**  
This tool is provided **only for educational and ethical testing on systems you own or have explicit permission to test**. Any misuse of this software is not the responsibility of the author. **Using it against unauthorized systems is illegal.**

## Features

- Multi-threaded request sending for maximum concurrency
- Randomized User-Agent headers to simulate different clients
- Custom target IP and port configuration
- Continuous traffic generation loop

## Requirements

- Python 3.x
- `requests` or other networking libraries (if added later)

## Usage

```bash
python3 main.py
