# Passport Photo Enhancer - Setup Guide

A modern web application that transforms regular photos into professional passport-ready images using AI-powered face detection and image enhancement.

## Features

✨ **Automatic Enhancements:**
- Background cleanup and replacement with white background
- Face detection and centering
- Correct passport-style cropping
- Brightness and sharpness optimization
- Passport-style framing (1200x1600px)

🎨 **Modern UI:**
- Clean, attractive React interface
- Drag-and-drop file upload
- Real-time preview
- Side-by-side comparison
- One-click download

## Technology Stack

**Backend:**
- FastAPI (Python web framework)
- OpenCV (Image processing)
- MediaPipe (Face detection)
- Rembg (Background removal)
- PIL/Pillow (Image enhancement)

**Frontend:**
- React 18
- Vite (Build tool)
- TailwindCSS (Styling)
- Lucide React (Icons)
- Axios (HTTP client)

## Windows one-click setup (recommended)

1. Install **Python 3.12** from [python.org](https://www.python.org/downloads/) and select **Add Python to PATH** during installation.
2. Install the current **Node.js LTS** version from [nodejs.org](https://nodejs.org/).
3. Download this repository as a ZIP and extract it completely. Do not run it from inside the ZIP.
4. Double-click **`setup_windows.bat`** once. Wait for the green `SETUP COMPLETE` message; the first setup can take 10–20 minutes and downloads a 176 MB AI model.
5. Double-click **`run_windows.bat`** whenever you want to use the app. It opens automatically at `http://127.0.0.1:3000`.
6. Keep the two Photo Enhancer command windows open while using the app. Double-click **`stop_windows.bat`** to close both services.

If setup fails, the installer keeps the error visible. Send a screenshot of the complete window for diagnosis. The corrected installer does not use the old `^<=` batch expression that caused the earlier Windows error.

## Prerequisites for manual setup

- Python 3.10–3.12 (Python 3.12 recommended)
- Node.js 18 or higher (current LTS recommended)
- npm or yarn

## Installation

### 1. Backend Setup

```bash
# Navigate to backend directory
cd backend

# Create virtual environment (recommended)
python -m venv venv

# Activate virtual environment
# On Windows:
venv\Scripts\activate
# On macOS/Linux:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Frontend Setup

```bash
# Navigate to frontend directory
cd frontend

# Install dependencies
npm install
```

## Running the Application

### Start Backend Server

```bash
# From backend directory with activated virtual environment
cd backend
python app.py
```

The API will be available at `http://localhost:8000`

### Start Frontend Development Server

```bash
# From frontend directory (in a new terminal)
cd frontend
npm run dev
```

The web app will be available at `http://localhost:3000`

## Usage

1. Open your browser and navigate to `http://localhost:3000`
2. Upload a photo by:
   - Clicking the upload area and selecting a file
   - Dragging and dropping an image
3. Click "Enhance Photo" to process the image
4. Download the processed passport photo

## Photo Guidelines

For best results, ensure your photo meets these requirements:

- **Face and Pose:** Look straight at camera, head centered, face filling most of frame
- **Expression:** Neutral expression, mouth closed, no smile
- **Eyes:** Open, clearly visible, looking at camera
- **Headwear:** No hats or caps (religious headwear may be acceptable)
- **Glasses:** Only if lenses are clear with no glare
- **Lighting:** Even front lighting, no strong shadows
- **Background:** Plain, light-colored background
- **Quality:** Sharp, in focus, no filters

## API Endpoints

### GET `/`
Returns API information and available endpoints

### POST `/process`
Process an uploaded image into a passport photo

**Request:**
- Content-Type: `multipart/form-data`
- Body: Image file

**Response:**
- Content-Type: `image/jpeg`
- Body: Processed passport photo

## Project Structure

```
image-enhancer/
├── backend/
│   ├── app.py              # FastAPI application
│   ├── requirements.txt    # Python dependencies
│   └── .gitignore
├── frontend/
│   ├── src/
│   │   ├── App.jsx        # Main React component
│   │   ├── main.jsx       # React entry point
│   │   └── index.css      # Global styles
│   ├── index.html
│   ├── package.json
│   ├── vite.config.js
│   ├── tailwind.config.js
│   └── postcss.config.js
├── sample.py              # Original standalone script
├── guidelines.jpeg        # Photo guidelines reference
└── README.md
```

## Building for Production

### Frontend

```bash
cd frontend
npm run build
```

The production-ready files will be in `frontend/dist/`

### Backend

For production deployment, use a production ASGI server:

```bash
pip install gunicorn
gunicorn -w 4 -k uvicorn.workers.UvicornWorker app:app
```

## Troubleshooting

**Issue:** "No face detected" error
- Ensure the photo contains a clearly visible face
- Check that lighting is adequate
- Make sure the face is not too small in the frame

**Issue:** Backend connection error
- Verify the backend server is running on port 8000
- Check CORS settings in `app.py`
- Ensure firewall allows local connections

**Issue:** Dependencies installation fails
- Update pip: `pip install --upgrade pip`
- For Windows, you may need Visual C++ Build Tools for some packages
- Try installing packages individually if bulk install fails

## Future Enhancements

- ICAO passport validation
- Automatic shadow removal
- Eye-level alignment detection
- Ear visibility checks
- Country-specific passport templates
- Batch processing
- User accounts and history
- Mobile app version

## License

This project is provided as-is for educational and personal use.

## Support

For issues or questions, please check the troubleshooting section or review the photo guidelines.
