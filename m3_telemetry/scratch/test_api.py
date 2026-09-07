import sys
from publisher.api import create_publisher, start_stream

received = []
pub = create_publisher("standard_day", "smooth")
start_stream(pub, lambda msg, f: received.append(msg), duration_s=0.5)

assert len(received) > 0, "No messages received!"
sys.exit(0)
