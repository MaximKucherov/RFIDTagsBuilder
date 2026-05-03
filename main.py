"""
RFIDTagBuilder v3 — Entry Point
"""
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)

from app import App

if __name__ == "__main__":
    App().run()
