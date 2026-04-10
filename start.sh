#!/bin/bash

echo "Starting DataWeaver..."

# Kill anything already on these ports
lsof -ti :8000 | xargs kill -9 2>/dev/null
lsof -ti :5173 | xargs kill -9 2>/dev/null

ROOT="$(cd "$(dirname "$0")" && pwd)"

# Start backend
cd "$ROOT/backend"
uvicorn main:app --reload --port 8000 &
BACKEND_PID=$!
echo "Backend started (PID $BACKEND_PID)"

# Start frontend
cd "$ROOT/frontend"
npm run dev &
FRONTEND_PID=$!
echo "Frontend started (PID $FRONTEND_PID)"

echo ""
echo "DataWeaver running at http://localhost:5173"
echo "Press Ctrl+C to stop both servers."

# Wait and clean up on exit
trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; echo 'Stopped.'" EXIT
wait
