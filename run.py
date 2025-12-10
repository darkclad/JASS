#!/usr/bin/env python
"""JASS Application Launcher with configurable logging."""
import argparse
import sys
import os

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from logger import setup_logging


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description='JASS - Job Application Support System',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Verbosity levels:
  (none)   Only errors
  -d       Errors + warnings
  -dd      + Info messages
  -ddd     + Debug messages
  -dddd    + Trace messages (very verbose)
  -ddddd   + All framework logs

Examples:
  python run.py              Run with minimal logging
  python run.py -dd          Run with info level logging
  python run.py -ddd         Run with debug level logging
  python run.py --port 8080  Run on port 8080
'''
    )

    parser.add_argument(
        '-d', '--debug',
        action='count',
        default=0,
        help='Increase verbosity (can be repeated: -d, -dd, -ddd, -dddd, -ddddd)'
    )

    parser.add_argument(
        '-p', '--port',
        type=int,
        default=5000,
        help='Port to run the server on (default: 5000)'
    )

    parser.add_argument(
        '--host',
        default='127.0.0.1',
        help='Host to bind to (default: 127.0.0.1, use 0.0.0.0 for all interfaces)'
    )

    parser.add_argument(
        '--no-reload',
        action='store_true',
        help='Disable auto-reload on code changes'
    )

    return parser.parse_args()


def main():
    """Main entry point."""
    args = parse_args()

    # Setup logging based on verbosity
    verbosity = min(args.debug, 5)  # Cap at 5
    log = setup_logging(verbosity)

    log.info(f"Starting JASS on {args.host}:{args.port}")
    log.debug(f"Verbosity level: {verbosity}")

    # Import app after logging is configured
    from app import app

    # Run the Flask app
    # Enable debug mode for Flask if verbosity >= 3
    flask_debug = verbosity >= 3

    try:
        app.run(
            host=args.host,
            port=args.port,
            debug=flask_debug,
            use_reloader=not args.no_reload and flask_debug
        )
    except KeyboardInterrupt:
        log.info("Shutting down...")
    except Exception as e:
        log.error(f"Failed to start server: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
