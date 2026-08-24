# OmniLaunge

OmniLaunge is a real-time virtual lounge app inspired by social metaverse spaces.
Users create avatars, move through rooms, chat in real time, and interact with world objects.

## What You Can Do

- Create a custom avatar (skin, hair, beard, glasses, clothes, accessories)
- Move via keyboard or click-to-walk
- Chat publicly or privately with other players
- Interact with room objects and radial menus
- Use combat controls (punch, kick, block) with stamina/KO systems
- Explore AI bot interactions and game-like room behavior

## Tech Stack

- Frontend: Vite, vanilla JavaScript, SVG avatar renderer, Socket.IO client
- Backend: Python, FastAPI, python-socketio
- Database: PostgreSQL (Docker Compose)
- Testing: Vitest (JS), pytest (Python)

## Documentation

Detailed, split documentation is available in:

- [docs/README.md](docs/README.md)

That index routes to feature-level and functionality-level documents, including architecture and runtime diagrams.

## Repository Structure

```text
client/                 Frontend app (Vite root)
	css/
	js/
server/                 FastAPI + Socket.IO backend
	db/
	game/
src/                    Shared JS domain logic (tested in Vitest)
tests/                  JS tests
tests_python/           Python tests
docker-compose.yml      Local PostgreSQL + backend services
requirements.txt        Python dependencies
package.json            Node scripts and dependencies
```

## Prerequisites

- Node.js 18+
- Python 3.11+
- Docker + Docker Compose

## Setup

```bash
# 1) Install Node dependencies
npm install

# 2) Install Python dependencies
pip install -r requirements.txt
```

## Run in Development

Start database, backend, and frontend together:

```bash
npm run dev
```

This runs:
- `docker compose up -d` (database and configured services)
- `python3 -m server.main` (backend on port 8000)
- `vite` (frontend on port 5173)

Open:
- Frontend: http://localhost:5173
- Backend: http://localhost:8000

Tip: Open two or more browser tabs/windows to test multiplayer behavior.

## Run with Docker Services Explicitly

```bash
# Start services
docker compose up -d

# Stop services
docker compose down

# Rebuild backend image
docker compose build server
docker compose up -d server
```

## Test

```bash
# Full test suite
npm test

# JS only
npm run test:js

# Python only
npm run test:python
```

If your local Python environment does not have `pytest`, install dependencies from `requirements.txt` first.

## Build and Run

```bash
# Build frontend assets
npm run build

# Run backend app
npm start
```

## Environment Notes

- Default PostgreSQL credentials are defined in `docker-compose.yml`:
	- User: `omnilaunge`
	- Password: `omnilaunge`
	- Database: `omnilaunge`
- Backend DB connection can be overridden via `DATABASE_URL`.

## Gameplay Controls

- Movement: Arrow keys or click on floor
- Combat:
	- `Space`: punch
	- `Ctrl`/`Cmd`: kick
	- `B`: block
- Chat: use public/private mode in chat panel

## Contributing

Contributions are welcome. Please follow this workflow:

1. Fork the repo (or create a branch if you have direct access).
2. Create a feature branch:

	 ```bash
	 git checkout -b feature/short-description
	 ```

3. Make focused changes.
4. Add or update tests for behavior changes.
5. Run full test suite locally:

	 ```bash
	 npm test
	 ```

6. Commit with clear messages:

	 ```bash
	 git commit -m "feat: add X"
	 ```

7. Push and open a Pull Request.

### Contribution Guidelines

- Keep PRs small and focused.
- Preserve existing coding style and folder conventions.
- Update documentation when behavior changes.
- Avoid unrelated refactors in feature/fix PRs.

## Troubleshooting

- Port already in use:
	- Check 5173, 8000, and 5432 for conflicts.
- No backend response:
	- Confirm Docker DB is up and backend process is running.
- Tests failing unexpectedly:
	- Reinstall dependencies and rerun targeted test commands.

## License

Add your preferred license file (for example MIT) if this repository will be public.
