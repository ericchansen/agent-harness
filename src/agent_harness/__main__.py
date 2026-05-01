"""Allow running as ``python -m agent_harness``."""

import sys

from agent_harness.agent import main

if __name__ == "__main__":
    sys.exit(main())
