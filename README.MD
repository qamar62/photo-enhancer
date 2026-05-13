# 📸 Passport Photo Enhancer

A modern web application that transforms regular photos into professional passport-ready images using AI-powered face detection and image enhancement.

![Status](https://img.shields.io/badge/status-ready-green) ![Python](https://img.shields.io/badge/python-3.8+-blue) ![React](https://img.shields.io/badge/react-18-blue)

## ✨ Features

### Automatic Enhancements
- ✅ Background cleanup and white background replacement
- ✅ Face detection and centering
- ✅ Correct passport-style cropping
- ✅ Brightness optimization
- ✅ Sharpness enhancement
- ✅ Passport-style framing (1200x1600px)

### Modern Web Interface
- 🎨 Clean, attractive React UI
- 📤 Drag-and-drop file upload
- 👁️ Real-time preview
- ⚡ Fast processing
- 💾 One-click download

## 🚀 Quick Start

### Prerequisites
- Python 3.8+
- Node.js 16+
- npm or yarn

### Installation & Running

**1. Backend Setup**
```bash
cd backend
python -m venv venv
venv\Scripts\activate  # Windows
pip install -r requirements.txt
python app.py
```

**2. Frontend Setup** (in new terminal)
```bash
cd frontend
npm install
npm run dev
```

**3. Open Browser**
Navigate to `http://localhost:3000`

📖 **For detailed setup instructions, see [SETUP.md](SETUP.md)**

## 🏗️ Project Structure

```
image-enhancer/
├── backend/          # FastAPI backend service
│   ├── app.py       # Main API application
│   └── requirements.txt
├── frontend/         # React web application
│   ├── src/
│   │   ├── App.jsx  # Main component
│   │   └── ...
│   └── package.json
├── sample.py         # Original standalone script
├── guidelines.jpeg   # Photo guidelines reference
└── SETUP.md         # Detailed setup guide
```

## 🎯 Usage

1. Upload a photo (drag & drop or click to browse)
2. Click "Enhance Photo"
3. Download your passport-ready image

## 📋 Photo Guidelines

For best results:
- **Face and Pose:** Look straight at camera, head centered
- **Expression:** Neutral, mouth closed, no smile
- **Eyes:** Open, clearly visible, no obstructions
- **Headwear:** No hats/caps (religious exceptions may apply)
- **Glasses:** Clear lenses only, no glare
- **Lighting:** Even, no strong shadows
- **Background:** Plain, light-colored
- **Quality:** Sharp, in focus, no filters

## 🛠️ Technology Stack

**Backend:**
- FastAPI - Modern Python web framework
- OpenCV - Image processing
- MediaPipe - Face detection
- Rembg - Background removal
- Pillow - Image enhancement

**Frontend:**
- React 18 - UI framework
- Vite - Build tool
- TailwindCSS - Styling
- Lucide React - Icons
- Axios - HTTP client

## 🔮 Future Enhancements

- [ ] ICAO passport validation
- [ ] Automatic shadow removal
- [ ] Eye-level alignment detection
- [ ] Ear visibility checks
- [ ] Country-specific templates
- [ ] Batch processing
- [ ] User accounts and history
- [ ] Mobile app version

## 📝 API Endpoints

- `GET /` - API information
- `POST /process` - Process uploaded image

API documentation available at `http://localhost:8000/docs`

## 🤝 Contributing

This project is open for improvements. Feel free to enhance features or fix issues.

## 📄 License

Provided as-is for educational and personal use."# photo-enhancer" 
