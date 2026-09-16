import { useState, useRef } from 'react'
import { Upload, Download, Image as ImageIcon, CheckCircle2, AlertCircle, Loader2, Camera } from 'lucide-react'
import axios from 'axios'

const API_URL = import.meta.env.PROD ? '/api' : 'http://localhost:8000'

function App() {
  const [selectedFile, setSelectedFile] = useState(null)
  const [previewUrl, setPreviewUrl] = useState(null)
  const [processedUrl, setProcessedUrl] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [success, setSuccess] = useState(false)
  const fileInputRef = useRef(null)
  
  const [removeBackground, setRemoveBackground] = useState(true)
  const [backgroundColor, setBackgroundColor] = useState('#FFFFFF')
  const [width, setWidth] = useState(1200)
  const [height, setHeight] = useState(1600)
  const [profile, setProfile] = useState('natural')
  const [strength, setStrength] = useState(70)
  const [autoCrop, setAutoCrop] = useState(true)

  const handleFileSelect = (e) => {
    const file = e.target.files[0]
    if (file) {
      if (!file.type.startsWith('image/')) {
        setError('Please select a valid image file')
        return
      }
      setSelectedFile(file)
      setPreviewUrl(URL.createObjectURL(file))
      setProcessedUrl(null)
      setError(null)
      setSuccess(false)
    }
  }

  const handleDrop = (e) => {
    e.preventDefault()
    const file = e.dataTransfer.files[0]
    if (file && file.type.startsWith('image/')) {
      setSelectedFile(file)
      setPreviewUrl(URL.createObjectURL(file))
      setProcessedUrl(null)
      setError(null)
      setSuccess(false)
    }
  }

  const handleDragOver = (e) => {
    e.preventDefault()
  }

  const handleProcess = async () => {
    if (!selectedFile) return

    setLoading(true)
    setError(null)
    setSuccess(false)

    const formData = new FormData()
    formData.append('file', selectedFile)

    const hexToRgb = (hex) => {
      const result = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex)
      return result ? {
        r: parseInt(result[1], 16),
        g: parseInt(result[2], 16),
        b: parseInt(result[3], 16)
      } : { r: 255, g: 255, b: 255 }
    }

    const rgb = hexToRgb(backgroundColor)

    const params = new URLSearchParams({
      remove_bg: removeBackground,
      bg_color_r: rgb.r,
      bg_color_g: rgb.g,
      bg_color_b: rgb.b,
      width: width,
      height: height,
      profile,
      strength: strength / 100,
      auto_crop: autoCrop
    })

    try {
      const response = await axios.post(`${API_URL}/process?${params}`, formData, {
        responseType: 'blob',
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      })

      const url = URL.createObjectURL(response.data)
      setProcessedUrl(url)
      setSuccess(true)
    } catch (err) {
      let message = 'Failed to process image. Please try again.'
      if (err.response?.data instanceof Blob) {
        try {
          const body = JSON.parse(await err.response.data.text())
          message = body.detail || message
        } catch (_) { /* keep friendly fallback */ }
      } else if (err.response?.data?.detail) {
        message = err.response.data.detail
      }
      setError(message)
    } finally {
      setLoading(false)
    }
  }

  const handleDownload = () => {
    if (processedUrl) {
      const link = document.createElement('a')
      link.href = processedUrl
      link.download = 'passport_photo.jpg'
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
    }
  }

  const handleReset = () => {
    setSelectedFile(null)
    setPreviewUrl(null)
    setProcessedUrl(null)
    setError(null)
    setSuccess(false)
    if (fileInputRef.current) {
      fileInputRef.current.value = ''
    }
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 via-white to-purple-50">
      <div className="container mx-auto px-4 py-8 max-w-7xl">
        <div className="text-center mb-12">
          <div className="flex items-center justify-center mb-4">
            <Camera className="w-12 h-12 text-primary mr-3" />
            <h1 className="text-5xl font-bold bg-gradient-to-r from-blue-600 to-purple-600 bg-clip-text text-transparent">
              Passport Photo Enhancer
            </h1>
          </div>
          <p className="text-lg text-muted-foreground max-w-2xl mx-auto">
            Transform your photos into professional passport-ready images with AI-powered enhancement
          </p>
        </div>

        <div className="grid lg:grid-cols-2 gap-8 mb-8">
          <div className="bg-white rounded-2xl shadow-xl p-8 border border-gray-100">
            <h2 className="text-2xl font-semibold mb-6 flex items-center">
              <Upload className="w-6 h-6 mr-2 text-primary" />
              Upload Photo
            </h2>

            {!previewUrl ? (
              <div
                onDrop={handleDrop}
                onDragOver={handleDragOver}
                onClick={() => fileInputRef.current?.click()}
                className="border-2 border-dashed border-gray-300 rounded-xl p-12 text-center cursor-pointer hover:border-primary hover:bg-blue-50 transition-all duration-200"
              >
                <ImageIcon className="w-16 h-16 mx-auto mb-4 text-gray-400" />
                <p className="text-lg font-medium text-gray-700 mb-2">
                  Drop your photo here or click to browse
                </p>
                <p className="text-sm text-gray-500">
                  Supports JPG, PNG, JPEG
                </p>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept="image/*"
                  onChange={handleFileSelect}
                  className="hidden"
                />
              </div>
            ) : (
              <div className="space-y-4">
                <div className="relative rounded-xl overflow-hidden border-2 border-gray-200">
                  <img
                    src={previewUrl}
                    alt="Preview"
                    className="w-full h-auto max-h-96 object-contain bg-gray-50"
                  />
                </div>
                <div className="flex gap-3">
                  <button
                    onClick={handleReset}
                    className="flex-1 px-4 py-3 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 transition-colors font-medium"
                  >
                    Choose Different Photo
                  </button>
                  <button
                    onClick={handleProcess}
                    disabled={loading}
                    className="flex-1 px-4 py-3 bg-primary text-white rounded-lg hover:bg-blue-700 transition-colors font-medium disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center"
                  >
                    {loading ? (
                      <>
                        <Loader2 className="w-5 h-5 mr-2 animate-spin" />
                        Processing...
                      </>
                    ) : (
                      'Enhance Photo'
                    )}
                  </button>
                </div>
              </div>
            )}

            {error && (
              <div className="mt-4 p-4 bg-red-50 border border-red-200 rounded-lg flex items-start">
                <AlertCircle className="w-5 h-5 text-red-500 mr-3 flex-shrink-0 mt-0.5" />
                <p className="text-red-700 text-sm">{error}</p>
              </div>
            )}

            {success && (
              <div className="mt-4 p-4 bg-green-50 border border-green-200 rounded-lg flex items-start">
                <CheckCircle2 className="w-5 h-5 text-green-500 mr-3 flex-shrink-0 mt-0.5" />
                <p className="text-green-700 text-sm">Photo processed successfully!</p>
              </div>
            )}

            <div className="mt-6 pt-6 border-t border-gray-200">
              <h3 className="text-lg font-semibold mb-1">Processing Options</h3>
              <p className="text-xs text-gray-500 mb-4">Natural mode preserves identity and real skin texture.</p>
              
              <div className="space-y-4">
                <div className="space-y-2">
                  <label className="block text-sm font-medium text-gray-700">Enhancement profile</label>
                  <div className="grid grid-cols-3 gap-2">
                    {[
                      ['natural', 'Natural', 'Best default'],
                      ['restore', 'Restore', 'Soft/old photos'],
                      ['document', 'Document', 'Extra clarity'],
                    ].map(([value, label, hint]) => (
                      <button
                        type="button"
                        key={value}
                        onClick={() => setProfile(value)}
                        className={`rounded-lg border px-2 py-2 text-left transition-colors ${profile === value ? 'border-blue-600 bg-blue-50 text-blue-800' : 'border-gray-200 hover:bg-gray-50'}`}
                      >
                        <span className="block text-sm font-semibold">{label}</span>
                        <span className="block text-[10px] text-gray-500">{hint}</span>
                      </button>
                    ))}
                  </div>
                </div>

                <div className="space-y-2">
                  <div className="flex items-center justify-between text-sm font-medium text-gray-700">
                    <label htmlFor="strength">Enhancement strength</label>
                    <span>{strength}%</span>
                  </div>
                  <input
                    id="strength"
                    type="range"
                    min="0"
                    max="100"
                    value={strength}
                    onChange={(e) => setStrength(Number(e.target.value))}
                    className="w-full accent-blue-600"
                  />
                </div>

                <label className="flex items-center cursor-pointer">
                  <input
                    type="checkbox"
                    checked={autoCrop}
                    onChange={(e) => setAutoCrop(e.target.checked)}
                    className="w-4 h-4 text-primary border-gray-300 rounded focus:ring-primary"
                  />
                  <span className="ml-2 text-sm font-medium text-gray-700">Auto-center face without stretching</span>
                </label>

                <div className="flex items-center justify-between">
                  <label className="flex items-center cursor-pointer">
                    <input
                      type="checkbox"
                      checked={removeBackground}
                      onChange={(e) => setRemoveBackground(e.target.checked)}
                      className="w-4 h-4 text-primary border-gray-300 rounded focus:ring-primary"
                    />
                    <span className="ml-2 text-sm font-medium text-gray-700">Remove Background</span>
                  </label>
                </div>

                {removeBackground && (
                  <div className="space-y-2">
                    <label className="block text-sm font-medium text-gray-700">
                      Background Color
                    </label>
                    <div className="flex items-center gap-3">
                      <input
                        type="color"
                        value={backgroundColor}
                        onChange={(e) => setBackgroundColor(e.target.value)}
                        className="h-10 w-20 rounded border border-gray-300 cursor-pointer"
                      />
                      <input
                        type="text"
                        value={backgroundColor}
                        onChange={(e) => setBackgroundColor(e.target.value)}
                        className="flex-1 px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-primary focus:border-transparent"
                        placeholder="#FFFFFF"
                      />
                    </div>
                  </div>
                )}

                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <label className="block text-sm font-medium text-gray-700">
                      Width (px)
                    </label>
                    <input
                      type="number"
                      value={width}
                      onChange={(e) => setWidth(parseInt(e.target.value) || 1200)}
                      min="100"
                      max="5000"
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-primary focus:border-transparent"
                    />
                  </div>
                  <div className="space-y-2">
                    <label className="block text-sm font-medium text-gray-700">
                      Height (px)
                    </label>
                    <input
                      type="number"
                      value={height}
                      onChange={(e) => setHeight(parseInt(e.target.value) || 1600)}
                      min="100"
                      max="5000"
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-primary focus:border-transparent"
                    />
                  </div>
                </div>

                <div className="flex gap-2 text-xs text-gray-500">
                  <button
                    onClick={() => { setWidth(1200); setHeight(1600); }}
                    className="px-3 py-1 bg-gray-100 rounded hover:bg-gray-200 transition-colors"
                  >
                    Standard (1200×1600)
                  </button>
                  <button
                    onClick={() => { setWidth(600); setHeight(600); }}
                    className="px-3 py-1 bg-gray-100 rounded hover:bg-gray-200 transition-colors"
                  >
                    Square (600×600)
                  </button>
                  <button
                    onClick={() => { setWidth(2000); setHeight(2000); }}
                    className="px-3 py-1 bg-gray-100 rounded hover:bg-gray-200 transition-colors"
                  >
                    Large (2000×2000)
                  </button>
                </div>
              </div>
            </div>
          </div>

          <div className="bg-white rounded-2xl shadow-xl p-8 border border-gray-100">
            <h2 className="text-2xl font-semibold mb-6 flex items-center">
              <CheckCircle2 className="w-6 h-6 mr-2 text-green-600" />
              Enhanced Result
            </h2>

            {processedUrl ? (
              <div className="space-y-4">
                <div className="relative rounded-xl overflow-hidden border-2 border-green-200">
                  <img
                    src={processedUrl}
                    alt="Processed"
                    className="w-full h-auto max-h-96 object-contain bg-white"
                  />
                </div>
                <button
                  onClick={handleDownload}
                  className="w-full px-4 py-3 bg-green-600 text-white rounded-lg hover:bg-green-700 transition-colors font-medium flex items-center justify-center"
                >
                  <Download className="w-5 h-5 mr-2" />
                  Download Passport Photo
                </button>
              </div>
            ) : (
              <div className="border-2 border-dashed border-gray-200 rounded-xl p-12 text-center h-full flex flex-col items-center justify-center min-h-[400px]">
                <ImageIcon className="w-16 h-16 mx-auto mb-4 text-gray-300" />
                <p className="text-gray-500">
                  Your enhanced passport photo will appear here
                </p>
              </div>
            )}
          </div>
        </div>

        <div className="bg-white rounded-2xl shadow-xl p-8 border border-gray-100">
          <h3 className="text-xl font-semibold mb-4 flex items-center">
            <Camera className="w-5 h-5 mr-2 text-primary" />
            Photo Guidelines
          </h3>
          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6 text-sm">
            <div className="space-y-2">
              <h4 className="font-semibold text-gray-900">Face and Pose</h4>
              <p className="text-gray-600">Look straight at the camera, head centered, face filling most of the frame.</p>
            </div>
            <div className="space-y-2">
              <h4 className="font-semibold text-gray-900">Expression</h4>
              <p className="text-gray-600">Keep a neutral expression with your mouth closed (no big smile, no visible teeth).</p>
            </div>
            <div className="space-y-2">
              <h4 className="font-semibold text-gray-900">Eyes</h4>
              <p className="text-gray-600">Eyes open, clearly visible, looking at the camera; no hair, frames, or shadows covering them.</p>
            </div>
            <div className="space-y-2">
              <h4 className="font-semibold text-gray-900">Headwear & Glasses</h4>
              <p className="text-gray-600">No hats/caps; glasses only if lenses are clear and no glare or dark tint.</p>
            </div>
            <div className="space-y-2">
              <h4 className="font-semibold text-gray-900">Lighting</h4>
              <p className="text-gray-600">Use even front lighting with no strong shadows on your face or background.</p>
            </div>
            <div className="space-y-2">
              <h4 className="font-semibold text-gray-900">Background & Quality</h4>
              <p className="text-gray-600">Plain light background; photo must be sharp, in focus, and without color filters.</p>
            </div>
          </div>
        </div>

        <div className="mt-8 text-center text-sm text-gray-500">
          <p>Identity-safe processing • No face generation • No geometry stretching • Natural skin texture</p>
        </div>
      </div>
    </div>
  )
}

export default App
