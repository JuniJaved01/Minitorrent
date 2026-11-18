"""
tracker/api.py  --  OWNER: ARBAB
A small read-only HTTP API (FastAPI) on top of the registry.
The dashboard calls these URLs every 2 seconds and gets JSON back.
"""

from fastapi import FastAPI  # the web framework


def create_app(registry):
    """Build the FastAPI app around an existing Registry object."""
    app = FastAPI(title="MiniTorrent Tracker API")  # the application object

    @app.get("/health")  # GET /health
    def health():
        return {"status": "ok"}  # used by the launcher to know the tracker is up

    @app.get("/peers")  # GET /peers
    def peers():
        return registry.peers_snapshot()  # every live peer with bitmap, speeds, last heartbeat

    @app.get("/files")  # GET /files
    def files():
        return registry.files_snapshot()  # every file with seeders, leechers, availability

    @app.get("/stats")  # GET /stats
    def stats():
        return registry.stats()  # overall numbers

    @app.get("/events")  # GET /events
    def events():
        return registry.events_snapshot()  # newest joins / timeouts / completions

    return app  # uvicorn serves this object
