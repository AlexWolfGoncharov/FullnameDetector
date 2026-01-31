#!/usr/bin/env python3
"""
Main entry point for Ukrainian Name Detection API.

This script handles:
1. Automatic setup (downloads models if needed)
2. Running the API server

Usage:
    python run.py              # Run with auto-setup
    python run.py --setup-only # Only run setup, don't start server
    python run.py --skip-setup # Skip setup, just start server
"""

import argparse
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def main():
    parser = argparse.ArgumentParser(
        description="Ukrainian Name Detection API",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python run.py                  # Auto-setup and run
    python run.py --setup-only     # Only download models
    python run.py --skip-setup     # Skip setup, run directly
    python run.py --port 8080      # Run on custom port
        """
    )
    parser.add_argument(
        "--setup-only",
        action="store_true",
        help="Only run setup (download models), don't start server"
    )
    parser.add_argument(
        "--skip-setup",
        action="store_true",
        help="Skip automatic setup"
    )
    parser.add_argument(
        "--host",
        type=str,
        default="0.0.0.0",
        help="Host to bind to (default: 0.0.0.0)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to listen on (default: 8000)"
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable auto-reload for development"
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Number of workers (default: 1, use >1 for production)"
    )

    args = parser.parse_args()

    # Setup phase
    if not args.skip_setup:
        print("=" * 60)
        print("Running automatic setup...")
        print("=" * 60)

        from app.setup import SetupManager
        setup = SetupManager()
        setup.setup_all()
        status = setup.verify_setup()

        print("\n" + "=" * 40)
        print("Setup Status:")
        print("=" * 40)
        for component, ok in status.items():
            emoji = "[OK]" if ok else "[MISSING]"
            print(f"  {emoji} {component}")
        print("=" * 40)

        if args.setup_only:
            print("\nSetup complete. Run without --setup-only to start the server.")
            return

    # Run server
    print("\n" + "=" * 60)
    print(f"Starting API server on http://{args.host}:{args.port}")
    print(f"Docs available at: http://localhost:{args.port}/docs")
    print("=" * 60 + "\n")

    import uvicorn

    if args.workers > 1:
        # Production mode with multiple workers
        uvicorn.run(
            "app.main:app",
            host=args.host,
            port=args.port,
            workers=args.workers,
            reload=False
        )
    else:
        # Development mode
        uvicorn.run(
            "app.main:app",
            host=args.host,
            port=args.port,
            reload=args.reload
        )


if __name__ == "__main__":
    main()
