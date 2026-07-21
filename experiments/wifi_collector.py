#!/usr/bin/env python3
"""Compatibility entry point for the packaged Collection CLI."""

from cyberbrein.collection.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
