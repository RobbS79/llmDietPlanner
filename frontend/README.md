# React Frontend

This is the React frontend for the LLM Diet Planner application.

## Development

To run the frontend in development mode:

```bash
cd frontend
npm install
npm start
```

This will start the development server on `http://localhost:3000`.

## Production Build

For production, the React app is built as part of the Docker build process. The built files are served by Django via WhiteNoise.

To build manually:

```bash
cd frontend
npm install
npm run build
```

The build output will be in the `frontend/build/` directory, which is served by Django.

## Structure

- `src/` - React source files
- `public/` - Static public files (index.html, etc.)
- `build/` - Production build output (generated, not committed to git)

