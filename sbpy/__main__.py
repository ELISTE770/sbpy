"""מאפשר `python -m sbpy ...` וגם הרצה ישירה."""

try:
    from .cli import main
except ImportError:
    from sbpy.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
