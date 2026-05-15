from pathlib import Path
import os

marker = Path(os.environ["MELON_STATE_DIR"]) / "broken-post-install.txt"
marker.write_text("post-install-ran", encoding="utf-8")
raise SystemExit(7)
