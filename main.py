import os
import sys

dashboard_dir = os.path.join(os.path.dirname(__file__), "dashboard")
sys.path.insert(0, dashboard_dir)
os.chdir(dashboard_dir)

os.environ.setdefault("PORT", "8000")

from app import app as application

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run(application, host="0.0.0.0", port=port)
