"""Vercel entrypoint: Spark-only persistence, bounded requests, no background loop."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'apps/api'))
from padeltime.cloud import app
