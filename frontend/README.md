# Passport Photo Enhancer - Frontend

Modern React web application for uploading and processing passport photos.

## Quick Start

```bash
# Install dependencies
npm install

# Run development server
npm run dev
```

App runs on `http://localhost:3000`

## Build for Production

```bash
npm run build
```

Output in `dist/` directory.

## Technologies

- **React 18**: UI framework
- **Vite**: Build tool and dev server
- **TailwindCSS**: Utility-first CSS
- **Lucide React**: Icon library
- **Axios**: HTTP client

## Configuration

Backend API URL is set in `src/App.jsx`:
```javascript
const API_URL = 'http://localhost:8000'
```

Change this for production deployment.
