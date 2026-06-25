import React, { useState, useEffect, useRef } from 'react';
import { Search, PlusCircle, AlertCircle, Home, CheckCircle2, MapPin, Camera, Loader2, Tag, Image as ImageIcon, LayoutGrid, Check, User, LogIn, LogOut, MessageSquareCode, X, Sparkles, Send, ScanLine } from 'lucide-react';

// ⚠️ CHANGE THIS LINK TO YOUR REAL RENDER URL ⚠️
const BACKEND_URL = "https://ai-matchmaker-api-kjky.onrender.com/"; 

export default function App() {
  const [currentView, setCurrentView] = useState('home');
  const [formType, setFormType] = useState(''); 
  
  // Reported Items State
  const [itemName, setItemName] = useState('');
  const [itemDescription, setItemDescription] = useState('');
  const [itemLocation, setItemLocation] = useState('');
  const [imageFile, setImageFile] = useState(null); 
  
  // Lists and Search State
  const [aiMatches, setAiMatches] = useState([]);
  const [browseItems, setBrowseItems] = useState([]);
  const [isProcessing, setIsProcessing] = useState(false);

  // New Profile States
  const [myReports, setMyReports] = useState([]);
  const [myClaims, setMyClaims] = useState([]);

  // Authentication States
  const [currentUser, setCurrentUser] = useState(null);
  const [authModalOpen, setAuthModalOpen] = useState(false);
  const [authMode, setAuthMode] = useState('login');
  const [authUsername, setAuthUsername] = useState('');
  const [authPassword, setAuthPassword] = useState('');
  const [authEmail, setAuthEmail] = useState('');

  // AI Chat Assistant States
  const [assistantOpen, setAssistantOpen] = useState(false);
  const [chatMessages, setChatMessages] = useState([
    { role: 'model', text: 'Hi! I am your AI MatchMaker Assistant. Tell me what you lost or found (e.g., "I lost a grey iPhone in the library"), and I will automatically draft your report!' }
  ]);
  const [chatInput, setChatInput] = useState('');
  const [extractedData, setExtractedData] = useState({ name: '', description: '', location: '', type: 'unknown' });
  const [chatLoading, setChatLoading] = useState(false);

  // Live Camera Scanner States
  const [isLiveScanning, setIsLiveScanning] = useState(false);
  const [liveTags, setLiveTags] = useState([]);
  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const scanIntervalRef = useRef(null);

  // Custom Notifications
  const [toast, setToast] = useState({ show: false, message: '', type: 'success' });
  const [confirmModal, setConfirmModal] = useState({ show: false, title: '', message: '', onConfirm: null });

  const chatEndRef = useRef(null);

  // Auto-scroll chat to bottom
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [chatMessages]);

  // Handle auto login on load
  useEffect(() => {
    const savedUser = localStorage.getItem('matchmaker_user');
    if (savedUser) {
      setCurrentUser(JSON.parse(savedUser));
    }
  }, []);

  const triggerToast = (msg, type = 'success') => {
    setToast({ show: true, message: msg, type });
    setTimeout(() => {
      setToast(prev => ({ ...prev, show: false }));
    }, 4000);
  };

  const goToHome = () => {
    setCurrentView('home');
    setItemName('');
    setItemDescription('');
    setItemLocation('');
    setImageFile(null); 
    stopLiveScan();
  };
  
  const handleReportClick = (type) => {
    if (!currentUser) {
      triggerToast("You must log in to report items!", "error");
      setAuthMode('login');
      setAuthModalOpen(true);
      return;
    }
    setFormType(type);
    setCurrentView(`report-${type}`);
  };

  const startLiveScan = async () => {
    if (!currentUser) {
      triggerToast("You must log in to use the AI Lens!", "error");
      setAuthMode('login');
      setAuthModalOpen(true);
      return;
    }
    setCurrentView('live-scanner');
    setIsLiveScanning(true);
    setLiveTags(['Warming up AI...']);
    
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" } });
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
      }
      scanIntervalRef.current = setInterval(captureAndAnalyze, 2000);
    } catch (err) {
      triggerToast("Camera access denied or unavailable", "error");
      goToHome();
    }
  };

  const stopLiveScan = () => {
    if (videoRef.current && videoRef.current.srcObject) {
      videoRef.current.srcObject.getTracks().forEach(track => track.stop());
    }
    clearInterval(scanIntervalRef.current);
    setIsLiveScanning(false);
    setLiveTags([]);
  };

  const captureAndAnalyze = async () => {
    if (!videoRef.current || !canvasRef.current) return;
    const video = videoRef.current;
    const canvas = canvasRef.current;
    const context = canvas.getContext('2d');
    
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    context.drawImage(video, 0, 0, canvas.width, canvas.height);
    
    canvas.toBlob(async (blob) => {
      if (!blob) return;
      const formData = new FormData();
      formData.append('file', blob, 'frame.jpg');
      
      try {
         const res = await fetch(`${BACKEND_URL}/analyze-frame`, { method: 'POST', body: formData });
         const data = await res.json();
         if (data.tags && data.tags.length > 0) {
           setLiveTags(data.tags);
         } else {
           setLiveTags(["Scanning..."]);
         }
      } catch(e) { 
         console.error("Frame drop"); 
      }
    }, 'image/jpeg');
  };

  const handleAuthSubmit = async (e) => {
    e.preventDefault();
    if (!authUsername || !authPassword) {
      triggerToast("Please fill in all credentials", "error");
      return;
    }

    try {
      if (authMode === 'register') {
        const res = await fetch(`${BACKEND_URL}/register`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ username: authUsername, password: authPassword, email: authEmail || `${authUsername}@example.com` })
        });
        const data = await res.json();
        if (res.ok) {
          triggerToast("Registration complete! Please log in.");
          setAuthMode('login');
        } else {
          triggerToast(data.detail || "Registration failed", "error");
        }
      } else {
        const res = await fetch(`${BACKEND_URL}/login`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ username: authUsername, password: authPassword })
        });
        const data = await res.json();
        if (res.ok) {
          const userPayload = { username: data.username, token: data.token };
          setCurrentUser(userPayload);
          localStorage.setItem('matchmaker_user', JSON.stringify(userPayload));
          triggerToast(`Welcome back, ${data.username}!`);
          setAuthModalOpen(false);
          setAuthPassword('');
        } else {
          triggerToast(data.detail || "Login failed", "error");
        }
      }
    } catch (err) {
      triggerToast("Could not connect to the auth server", "error");
    }
  };

  const handleLogout = async () => {
    try {
      if (currentUser?.token) {
        await fetch(`${BACKEND_URL}/logout`, {
          method: 'POST',
          headers: { 'Authorization': `Bearer ${currentUser.token}` }
        });
      }
    } catch (e) {}
    setCurrentUser(null);
    localStorage.removeItem('matchmaker_user');
    goToHome();
    triggerToast("You have logged out.");
  };

  const loadBrowseFeed = async () => {
    setCurrentView('browse');
    setIsProcessing(true);
    try {
      const res = await fetch(`${BACKEND_URL}/items`);
      const data = await res.json();
      setBrowseItems(data.items);
    } catch (err) {
      triggerToast("Backend offline or waking up. Try again in 30 seconds!", "error");
    }
    setIsProcessing(false);
  };

  const loadProfile = async () => {
    if (!currentUser) return;
    setCurrentView('profile');
    setIsProcessing(true);
    try {
      const res = await fetch(`${BACKEND_URL}/profile`, {
        headers: { 'Authorization': `Bearer ${currentUser.token}` }
      });
      const data = await res.json();
      setMyReports(data.reports || []);
      setMyClaims(data.claims || []);
    } catch (err) {
      triggerToast("Failed to load profile", "error");
    }
    setIsProcessing(false);
  };

  const triggerClaimConfirm = (itemId) => {
    if (!currentUser) {
      triggerToast("You must log in to claim an item!", "error");
      setAuthMode('login');
      setAuthModalOpen(true);
      return;
    }
    setConfirmModal({
      show: true,
      title: "Claim Item",
      message: "Are you sure this item belongs to you? This action will mark it as claimed and connect you with the finder.",
      onConfirm: () => executeClaim(itemId)
    });
  };

  const executeClaim = async (itemId) => {
    setConfirmModal(prev => ({ ...prev, show: false }));
    try {
      const headers = currentUser ? { 'Authorization': `Bearer ${currentUser.token}` } : {};
      const res = await fetch(`${BACKEND_URL}/claim/${itemId}`, { 
        method: 'POST',
        headers: headers
      });
      if (res.ok) {
        triggerToast("Successfully claimed! A virtual message has been sent to the finder.");
        setAiMatches(prev => prev.filter(m => m.item.id !== itemId));
        setBrowseItems(prev => prev.filter(i => i.id !== itemId));
      } else {
        triggerToast("Failed to claim item", "error");
      }
    } catch (err) {
      triggerToast("Network error claiming item", "error");
    }
  };

  const handleSubmit = async (e) => {
    if (e) e.preventDefault();
    setIsProcessing(true);

    const formData = new FormData();
    formData.append("name", itemName);
    formData.append("description", itemDescription);
    formData.append("location", itemLocation);
    formData.append("type", formType);
    if (imageFile) formData.append("file", imageFile);

    const headers = currentUser ? { 'Authorization': `Bearer ${currentUser.token}` } : {};

    try {
      if (formType === 'found') {
        const res = await fetch(`${BACKEND_URL}/add-item`, { 
          method: 'POST', 
          headers: headers,
          body: formData 
        });
        if (res.ok) {
          triggerToast("Success! Item registered into the platform database.");
          goToHome();
        } else {
          triggerToast("Error reporting found item", "error");
        }
      } else if (formType === 'lost') {
        const response = await fetch(`${BACKEND_URL}/scan-matches`, { 
          method: 'POST', 
          headers: headers,
          body: formData 
        });
        const data = await response.json();
        setAiMatches(data.results);
        setCurrentView('dashboard');
      }
    } catch (error) {
      triggerToast("Error connecting to backend.", "error");
    }
    setIsProcessing(false);
  };

  const handleAssistantSend = async (e) => {
    e.preventDefault();
    if (!chatInput.trim()) return;

    const userMsg = chatInput;
    setChatMessages(prev => [...prev, { role: 'user', text: userMsg }]);
    setChatInput('');
    setChatLoading(true);

    const formattedHistory = chatMessages.map(m => ({
      role: m.role,
      text: m.text
    }));

    try {
      const response = await fetch(`${BACKEND_URL}/assistant/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: userMsg, history: formattedHistory })
      });
      const data = await response.json();

      setChatMessages(prev => [...prev, { role: 'model', text: data.reply }]);
      
      const newExtracted = {
        name: data.name || extractedData.name,
        description: data.description || extractedData.description,
        location: data.location || extractedData.location,
        type: data.type !== 'unknown' ? data.type : extractedData.type
      };
      setExtractedData(newExtracted);
    } catch (err) {
      setChatMessages(prev => [...prev, { role: 'model', text: "Whoops, my system hit a connection hitch. Are you sure our server is up?" }]);
    }
    setChatLoading(false);
  };

  const handlePublishAssistantDraft = async () => {
    if (!extractedData.name || !extractedData.location) {
      triggerToast("Please chat more with the assistant until at least Name and Location are found!", "error");
      return;
    }

    setIsProcessing(true);
    const formData = new FormData();
    formData.append("name", extractedData.name);
    formData.append("description", extractedData.description || "Reported via AI Assistant");
    formData.append("location", extractedData.location);
    formData.append("type", extractedData.type === 'unknown' ? 'lost' : extractedData.type);

    const headers = currentUser ? { 'Authorization': `Bearer ${currentUser.token}` } : {};

    try {
      if (extractedData.type === 'found') {
        const res = await fetch(`${BACKEND_URL}/add-item`, { 
          method: 'POST', 
          headers: headers,
          body: formData 
        });
        if (res.ok) {
          triggerToast("Report published successfully using AI extraction!");
          setAssistantOpen(false);
          setExtractedData({ name: '', description: '', location: '', type: 'unknown' });
          goToHome();
        }
      } else {
        const response = await fetch(`${BACKEND_URL}/scan-matches`, { 
          method: 'POST', 
          headers: headers,
          body: formData 
        });
        const data = await response.json();
        setAiMatches(data.results);
        setAssistantOpen(false);
        setExtractedData({ name: '', description: '', location: '', type: 'unknown' });
        setCurrentView('dashboard');
      }
    } catch (err) {
      triggerToast("Error publishing AI draft", "error");
    }
    setIsProcessing(false);
  };

  return (
    <div className="min-h-screen flex flex-col bg-gray-50 font-sans transition-all relative">
      
      {/* TOAST SYSTEM */}
      {toast.show && (
        <div className={`fixed bottom-6 right-6 z-50 p-4 rounded-2xl shadow-2xl flex items-center gap-3 animate-bounce border text-white transition-all ${
          toast.type === 'error' ? 'bg-rose-600 border-rose-500' : 'bg-emerald-600 border-emerald-500'
        }`}>
          {toast.type === 'error' ? <AlertCircle className="h-6 w-6" /> : <CheckCircle2 className="h-6 w-6" />}
          <span className="font-bold">{toast.message}</span>
        </div>
      )}

      {/* CONFIRMATION MODAL */}
      {confirmModal.show && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm animate-fade-in">
          <div className="bg-white rounded-3xl p-8 max-w-md w-full shadow-2xl border border-gray-100 animate-scale-up">
            <h3 className="text-2xl font-black text-gray-900 mb-3">{confirmModal.title}</h3>
            <p className="text-gray-600 mb-6">{confirmModal.message}</p>
            <div className="flex gap-4">
              <button 
                onClick={() => setConfirmModal({ show: false })}
                className="flex-1 py-3 px-4 bg-gray-100 hover:bg-gray-200 text-gray-700 font-bold rounded-xl transition"
              >
                Cancel
              </button>
              <button 
                onClick={confirmModal.onConfirm}
                className="flex-1 py-3 px-4 bg-indigo-600 hover:bg-indigo-700 text-white font-bold rounded-xl shadow-lg transition"
              >
                Confirm
              </button>
            </div>
          </div>
        </div>
      )}

      {/* NAVBAR */}
      <nav className="bg-indigo-600 text-white p-4 shadow-md flex justify-between items-center sticky top-0 z-30">
        <div className="flex items-center space-x-2 cursor-pointer" onClick={goToHome}>
          <Search className="h-6 w-6" />
          <span className="text-xl font-bold tracking-wider">AI MatchMaker</span>
        </div>
        <div className="flex items-center gap-2 sm:gap-4">
          <button onClick={loadBrowseFeed} className="flex items-center space-x-1 hover:text-indigo-200 transition bg-indigo-700/50 px-4 py-2 rounded-lg">
            <LayoutGrid className="h-5 w-5" /><span className="hidden sm:inline">Browse Feed</span>
          </button>
          
          {currentUser ? (
            <div className="flex items-center gap-2 bg-indigo-800/80 px-4 py-2 rounded-xl">
              <button onClick={loadProfile} className="flex items-center gap-1 hover:text-emerald-300 transition cursor-pointer">
                <User className="h-4 w-4 text-emerald-300" />
                <span className="text-sm font-bold max-w-[80px] sm:max-w-[150px] truncate">{currentUser.username}</span>
              </button>
              <button onClick={handleLogout} title="Log Out" className="hover:text-rose-300 ml-2">
                <LogOut className="h-4 w-4" />
              </button>
            </div>
          ) : (
            <button onClick={() => { setAuthMode('login'); setAuthModalOpen(true); }} className="flex items-center gap-1 bg-emerald-500 hover:bg-emerald-600 text-white px-4 py-2 rounded-xl font-bold transition shadow">
              <LogIn className="h-4 w-4" />
              <span>Log In</span>
            </button>
          )}

          {currentView !== 'home' && (
            <button onClick={goToHome} className="flex items-center space-x-1 hover:text-indigo-200 transition bg-indigo-700 px-4 py-2 rounded-lg">
              <Home className="h-5 w-5" /><span className="hidden sm:inline">Home</span>
            </button>
          )}
        </div>
      </nav>

      {/* MAIN SCREEN ROUTING */}
      <main className="flex-1 pb-12">
        {/* HOME VIEW */}
        {currentView === 'home' && (
          <div className="flex flex-col items-center justify-center min-h-[80vh] p-6 text-center animate-in fade-in duration-500">
            <div className="bg-indigo-100 text-indigo-700 px-4 py-1.5 rounded-full font-bold text-sm mb-6 flex items-center gap-2">
              <Sparkles className="h-4 w-4 text-yellow-500" /> Supercharged Conversational AI Live
            </div>
            <h1 className="text-4xl md:text-6xl font-black text-gray-900 mb-6 tracking-tight">
              Lost it? <span className="text-indigo-600">Let AI find it.</span>
            </h1>
            <p className="text-lg text-gray-600 mb-12 max-w-2xl">
              Upload a photo, scan with your live camera, or chat directly with our Matchmaker AI Assistant in the bottom right corner!
            </p>
            <div className="flex flex-col md:flex-row gap-6 w-full max-w-5xl">
              <button onClick={() => handleReportClick('lost')} className="group flex-1 flex flex-col items-center p-10 bg-white border-2 border-gray-100 rounded-3xl hover:border-red-400 hover:shadow-2xl transition-all cursor-pointer">
                <AlertCircle className="h-20 w-20 text-red-500 mb-4" />
                <span className="text-2xl font-bold text-gray-900">I Lost an Item</span>
              </button>
              
              <button onClick={startLiveScan} className="group flex-1 flex flex-col items-center p-10 bg-gradient-to-br from-indigo-500 to-purple-600 text-white border-2 border-indigo-400 rounded-3xl hover:shadow-2xl hover:scale-105 transition-all cursor-pointer relative overflow-hidden shadow-lg">
                <div className="absolute top-0 right-0 p-3 bg-red-500 text-white text-xs font-bold rounded-bl-xl animate-pulse">LIVE</div>
                <ScanLine className="h-20 w-20 text-white mb-4" /> 
                <span className="text-2xl font-bold">Live AI Lens</span>
              </button>

              <button onClick={() => handleReportClick('found')} className="group flex-1 flex flex-col items-center p-10 bg-white border-2 border-gray-100 rounded-3xl hover:border-green-400 hover:shadow-2xl transition-all cursor-pointer">
                <PlusCircle className="h-20 w-20 text-green-500 mb-4" />
                <span className="text-2xl font-bold text-gray-900">I Found an Item</span>
              </button>
            </div>
          </div>
        )}

        {/* LIVE SCANNER VIEW */}
        {currentView === 'live-scanner' && (
          <div className="max-w-4xl mx-auto p-6 mt-8 animate-in slide-in-from-bottom-4">
             <div className="bg-black rounded-3xl overflow-hidden relative shadow-2xl border-4 border-indigo-500">
               <div className="absolute top-4 left-4 z-10 flex gap-2">
                 <div className="bg-red-500 text-white px-3 py-1 rounded-full text-sm font-bold flex items-center gap-2 animate-pulse">
                   <div className="h-2 w-2 bg-white rounded-full"></div> LIVE
                 </div>
               </div>
               
               <button onClick={goToHome} className="absolute top-4 right-4 z-10 bg-white/20 hover:bg-white/40 backdrop-blur p-2 rounded-full text-white transition-all">
                 <X className="h-6 w-6" />
               </button>

               <video ref={videoRef} autoPlay playsInline className="w-full h-[60vh] object-cover" />
               <canvas ref={canvasRef} className="hidden" />

               <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black/90 to-transparent p-8 pt-20">
                 <h3 className="text-indigo-400 font-bold text-sm tracking-widest uppercase mb-2">AI Real-Time Detection</h3>
                 <div className="flex flex-wrap gap-3">
                   {liveTags.map((tag, i) => (
                     <span key={i} className="bg-white/20 backdrop-blur-md border border-white/40 text-white text-xl font-black px-4 py-2 rounded-xl">
                       {tag}
                     </span>
                   ))}
                 </div>
               </div>
             </div>
             <p className="text-center mt-6 text-gray-500 font-bold">Point your camera at objects. The AI analyzes 1 frame every 2 seconds.</p>
          </div>
        )}

        {/* MANUAL REPORT FORM */}
        {(currentView === 'report-lost' || currentView === 'report-found') && (
          <div className="max-w-xl mx-auto p-8 mt-12 bg-white rounded-3xl shadow-xl border border-gray-100 animate-in slide-in-from-bottom-4 duration-500">
            <h2 className="text-3xl font-black text-gray-800 mb-8 text-center flex items-center justify-center gap-3">
              {formType === 'lost' ? <AlertCircle className="text-red-500 h-8 w-8" /> : <PlusCircle className="text-green-500 h-8 w-8" />}
              {formType === 'lost' ? 'Report Lost Item' : 'Report Found Item'}
            </h2>
            <form onSubmit={handleSubmit} className="space-y-6">
              <div>
                <label className="block text-sm font-bold text-gray-700 mb-2">Item Name</label>
                <input type="text" required value={itemName} onChange={(e) => setItemName(e.target.value)} placeholder="E.g., Black iPhone 15" className="w-full p-4 border border-gray-200 rounded-xl bg-gray-50 text-lg" />
              </div>
              <div>
                <label className="block text-sm font-bold text-gray-700 mb-2">Description</label>
                <textarea required value={itemDescription} onChange={(e) => setItemDescription(e.target.value)} placeholder="E.g., It has a dark grey case, three cameras on the back..." className="w-full p-4 border border-gray-200 rounded-xl bg-gray-50 h-32 text-lg"></textarea>
              </div>
              <div>
                <label className="block text-sm font-bold text-gray-700 mb-2">Location</label>
                <div className="relative">
                  <MapPin className="absolute left-4 top-4 h-6 w-6 text-gray-400" />
                  <input type="text" required value={itemLocation} onChange={(e) => setItemLocation(e.target.value)} placeholder="E.g., Central Park, New York" className="w-full pl-12 p-4 border border-gray-200 rounded-xl bg-gray-50 text-lg" />
                </div>
              </div>

              <label className="border-2 border-dashed border-indigo-200 bg-indigo-50/50 rounded-2xl p-8 flex flex-col items-center cursor-pointer hover:bg-indigo-100 transition-colors">
                {imageFile ? <ImageIcon className="h-8 w-8 text-indigo-600 mb-2" /> : <Camera className="h-8 w-8 text-indigo-600 mb-2" />}
                <span className="text-sm text-indigo-700 font-bold text-center">
                  {imageFile ? imageFile.name : "Upload a photo (Boosts AI Accuracy!)"}
                </span>
                <input type="file" accept="image/*" className="hidden" onChange={(e) => setImageFile(e.target.files[0])} />
              </label>

              <button type="submit" disabled={isProcessing} className="w-full flex justify-center items-center gap-3 bg-indigo-600 text-white font-bold text-xl p-5 rounded-2xl hover:bg-indigo-700 transition-all disabled:bg-indigo-400">
                {isProcessing ? <Loader2 className="h-6 w-6 animate-spin" /> : null}
                {formType === 'lost' ? 'Scan Database for Matches' : 'Add to Database'}
              </button>
            </form>
          </div>
        )}

        {/* FEED / DASHBOARD VIEW */}
        {(currentView === 'dashboard' || currentView === 'browse') && (
          <div className="max-w-6xl mx-auto p-6 mt-8 animate-in slide-in-from-bottom-4 duration-500">
            {currentView === 'dashboard' ? (
              <div className="bg-gradient-to-r from-indigo-500 to-purple-600 rounded-3xl p-8 mb-10 text-center text-white shadow-lg">
                <CheckCircle2 className="h-16 w-16 text-white/90 mx-auto mb-4" />
                <h2 className="text-3xl font-black mb-2">Scan Complete!</h2>
                <p className="text-indigo-100 text-lg">Top AI matches based on visual and text similarity.</p>
              </div>
            ) : (
              <div className="mb-10">
                <h2 className="text-4xl font-black text-gray-900 mb-2">Live Public Feed</h2>
                <p className="text-gray-600 text-lg">Browse all active lost and found items in the ecosystem.</p>
              </div>
            )}
            
            {isProcessing && <Loader2 className="h-12 w-12 animate-spin text-indigo-500 mx-auto" />}

            <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-8">
              {(currentView === 'dashboard' ? aiMatches : browseItems).map((data, idx) => {
                const item = currentView === 'dashboard' ? data.item : data;
                const score = currentView === 'dashboard' ? data.confidence_score : null;

                return (
                  <div key={idx} className="bg-white border border-gray-200 rounded-3xl shadow-sm overflow-hidden flex flex-col hover:shadow-xl transition-all group">
                    {item.image_url ? (
                      <div className="relative h-56 bg-gray-100 overflow-hidden">
                        <img src={item.image_url} alt={item.name} className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500" />
                        <div className="absolute top-3 right-3 bg-white/90 backdrop-blur text-purple-700 text-xs font-bold px-3 py-1.5 rounded-full flex items-center gap-1">
                          <Camera className="h-3 w-3"/> AI Tagged
                        </div>
                      </div>
                    ) : (
                      <div className="h-24 bg-gray-50 flex items-center justify-center border-b border-gray-100">
                        <span className="text-gray-400 text-sm font-medium">No photo available</span>
                      </div>
                    )}
                    
                    <div className="p-6 flex-1 flex flex-col">
                      <div className="flex justify-between items-start mb-3">
                        <h4 className="text-2xl font-black text-gray-900 line-clamp-1">{item.name}</h4>
                        {score && (
                          <span className={`px-3 py-1 rounded-lg text-sm font-black shadow-sm ${score >= 70 ? 'bg-green-500 text-white' : 'bg-yellow-400 text-yellow-900'}`}>
                            {score}% Match
                          </span>
                        )}
                        {!score && (
                          <span className={`px-3 py-1 rounded-lg text-xs font-bold uppercase tracking-wide ${
                            item.type === 'found' ? 'bg-green-100 text-green-800' : 'bg-rose-100 text-rose-800'
                          }`}>
                            {item.type}
                          </span>
                        )}
                      </div>
                      
                      <p className="text-gray-600 mb-6 text-sm line-clamp-2">{item.description}</p>
                      
                      <div className="mb-6 rounded-xl overflow-hidden border border-gray-200 shadow-inner bg-gray-100">
                        <iframe 
                          width="100%" 
                          height="120" 
                          frameBorder="0" 
                          style={{ border: 0 }} 
                          src={`https://maps.google.com/maps?q=${encodeURIComponent(item.location)}&t=&z=14&ie=UTF8&iwloc=&output=embed`} 
                          allowFullScreen
                        ></iframe>
                        <div className="bg-white p-2 text-xs text-gray-600 font-bold flex items-center gap-1 border-t border-gray-200">
                          <MapPin className="h-3 w-3 text-red-500" /> {item.location}
                        </div>
                      </div>

                      <div className="mt-auto flex flex-col gap-2">
                        <button 
                          onClick={() => triggerClaimConfirm(item.id)}
                          className="w-full py-3 bg-green-50 hover:bg-green-500 hover:text-white text-green-700 font-bold rounded-xl transition-colors border border-green-200 hover:border-green-500 flex items-center justify-center gap-2"
                        >
                          <Check className="h-5 w-5" /> YES! This is mine.
                        </button>
                        <div className="text-[10px] text-gray-400 text-center">
                          Posted by: <span className="font-bold text-gray-500">{item.creator || 'anonymous'}</span>
                        </div>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* MY PROFILE VIEW (NEW) */}
        {currentView === 'profile' && (
          <div className="max-w-6xl mx-auto p-6 mt-8 animate-in slide-in-from-bottom-4 duration-500">
            <div className="bg-indigo-600 rounded-3xl p-8 mb-10 text-white shadow-lg flex items-center gap-6">
              <div className="bg-white/20 p-4 rounded-full">
                <User className="h-12 w-12 text-white" />
              </div>
              <div>
                <h2 className="text-3xl font-black mb-1">{currentUser?.username}'s Dashboard</h2>
                <p className="text-indigo-200 text-lg">Manage your reports and connect with finders.</p>
              </div>
            </div>

            {isProcessing && <Loader2 className="h-12 w-12 animate-spin text-indigo-500 mx-auto mb-8" />}

            <h3 className="text-2xl font-black text-gray-900 mb-6 border-b pb-2 border-gray-200">Items I've Claimed</h3>
            {myClaims.length === 0 ? (
              <p className="text-gray-500 mb-10 italic bg-white p-6 rounded-2xl border border-gray-100 shadow-sm">You haven't claimed any items yet.</p>
            ) : (
              <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-8 mb-12">
                {myClaims.map((item, idx) => (
                  <div key={idx} className="bg-white border-2 border-green-400 rounded-3xl p-6 shadow-md flex flex-col relative overflow-hidden group hover:shadow-xl transition-all">
                    <div className="absolute top-0 right-0 bg-green-500 text-white text-xs font-bold px-3 py-1.5 rounded-bl-xl shadow-sm">
                      <CheckCircle2 className="h-3 w-3 inline mr-1"/> Claimed
                    </div>
                    <h4 className="text-2xl font-black text-gray-900 mb-2 mt-2">{item.name}</h4>
                    <p className="text-gray-600 mb-6 line-clamp-2 text-sm">{item.description}</p>
                    <div className="mt-auto bg-green-50/50 p-4 rounded-xl border border-green-100">
                      <p className="text-xs font-bold text-green-800 uppercase tracking-wider mb-2">Connect with Finder</p>
                      <p className="text-sm text-gray-700 mb-1">Found by: <span className="font-bold">{item.creator}</span></p>
                      <p className="font-black text-green-700 text-sm break-all">✉️ {item.creator}@matchmaker.app</p>
                    </div>
                  </div>
                ))}
              </div>
            )}

            <h3 className="text-2xl font-black text-gray-900 mb-6 border-b pb-2 border-gray-200">Items I've Reported</h3>
            {myReports.length === 0 ? (
              <p className="text-gray-500 mb-10 italic bg-white p-6 rounded-2xl border border-gray-100 shadow-sm">You haven't reported any items yet.</p>
            ) : (
              <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-8 mb-10">
                {myReports.map((item, idx) => (
                  <div key={idx} className={`bg-white border-2 rounded-3xl p-6 shadow-sm flex flex-col relative transition-all hover:shadow-lg ${item.status === 'claimed' ? 'border-indigo-400 bg-indigo-50/10' : 'border-gray-200'}`}>
                    {item.status === 'claimed' && (
                      <div className="absolute top-0 right-0 bg-indigo-500 text-white text-xs font-bold px-3 py-1.5 rounded-bl-xl shadow-sm animate-pulse">
                        <Sparkles className="h-3 w-3 inline mr-1"/> Claimed by User!
                      </div>
                    )}
                    <h4 className="text-2xl font-black text-gray-900 mb-2 mt-2">{item.name}</h4>
                    <p className="text-gray-600 mb-6 line-clamp-2 text-sm">{item.description}</p>
                    <div className={`mt-auto p-4 rounded-xl ${item.status === 'claimed' ? 'bg-indigo-50 border border-indigo-100' : 'bg-gray-50 border border-gray-100'}`}>
                      <p className="text-sm font-bold text-gray-800">Status: <span className={item.status === 'claimed' ? 'text-indigo-600' : 'text-emerald-600'}>{item.status.toUpperCase()}</span></p>
                      {item.status === 'claimed' && (
                        <div className="mt-3 pt-3 border-t border-indigo-200">
                          <p className="text-xs text-indigo-800 uppercase tracking-wider font-bold mb-1">Claimant Info</p>
                          <p className="text-sm font-black text-indigo-700">{item.claimed_by}@matchmaker.app</p>
                        </div>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </main>

      {/* FOOTER */}
      <footer className="bg-gray-900 text-gray-400 py-8 text-center mt-auto">
        <div className="max-w-4xl mx-auto px-6">
          <p className="font-medium text-gray-300 mb-2">Built with React, Python FastAPI, and Computer Vision</p>
          <p className="text-sm">© 2026 AI MatchMaker Enterprise Edition. All rights reserved.</p>
        </div>
      </footer>

      {/* FLOAT AI ASSISTANT WIDGET TOGGLE BUTTON */}
      <button 
        onClick={() => {
          if (!currentUser) {
            triggerToast("You must log in to use the AI Assistant!", "error");
            setAuthMode('login');
            setAuthModalOpen(true);
            return;
          }
          setAssistantOpen(true);
        }}
        className="fixed bottom-6 left-6 z-40 bg-gradient-to-tr from-indigo-600 to-purple-600 text-white p-5 rounded-full shadow-2xl hover:scale-110 active:scale-95 hover:rotate-3 transition-all flex items-center gap-2 border border-indigo-400 group"
      >
        <MessageSquareCode className="h-7 w-7 animate-pulse" />
        <span className="max-w-0 overflow-hidden group-hover:max-w-[150px] transition-all duration-300 font-black text-sm uppercase tracking-wider">
          AI Assistant
        </span>
      </button>

      {/* FLOAT CHAT ASSISTANT PANEL */}
      {assistantOpen && (
        <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-end p-4 bg-black/60 backdrop-blur-sm animate-fade-in">
          <div className="bg-white w-full max-w-4xl h-[90vh] sm:h-[80vh] rounded-t-3xl sm:rounded-3xl shadow-2xl overflow-hidden flex flex-col md:flex-row animate-scale-up">
            
            <div className="flex-1 flex flex-col h-1/2 md:h-full border-b md:border-b-0 md:border-r border-gray-200">
              <div className="p-4 bg-gradient-to-r from-indigo-600 to-purple-600 text-white flex justify-between items-center">
                <div className="flex items-center gap-2 font-black text-lg">
                  <Sparkles className="h-5 w-5 text-yellow-300 animate-spin" />
                  <span>MatchMaker Conversational AI</span>
                </div>
                <button onClick={() => setAssistantOpen(false)} className="text-white hover:text-gray-200">
                  <X className="h-6 w-6" />
                </button>
              </div>

              <div className="flex-1 overflow-y-auto p-4 space-y-4 bg-gray-50">
                {chatMessages.map((msg, idx) => (
                  <div key={idx} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                    <div className={`max-w-[80%] rounded-2xl p-4 text-sm shadow-sm font-medium leading-relaxed ${
                      msg.role === 'user' 
                        ? 'bg-indigo-600 text-white rounded-br-none' 
                        : 'bg-white text-gray-800 border border-gray-100 rounded-bl-none'
                    }`}>
                      {msg.text}
                    </div>
                  </div>
                ))}
                {chatLoading && (
                  <div className="flex justify-start">
                    <div className="bg-white border border-gray-100 rounded-2xl rounded-bl-none p-4 shadow-sm flex items-center gap-2 text-gray-500 text-xs">
                      <Loader2 className="h-4 w-4 animate-spin text-indigo-500" />
                      <span>AI is reading your details...</span>
                    </div>
                  </div>
                )}
                <div ref={chatEndRef} />
              </div>

              <form onSubmit={handleAssistantSend} className="p-3 bg-white border-t border-gray-100 flex gap-2">
                <input 
                  type="text" 
                  value={chatInput} 
                  onChange={(e) => setChatInput(e.target.value)}
                  placeholder="Tell the AI what you lost/found..."
                  className="flex-1 p-3 border border-gray-200 rounded-xl bg-gray-50 focus:ring-2 focus:ring-indigo-500 focus:outline-none"
                />
                <button type="submit" className="bg-indigo-600 hover:bg-indigo-700 text-white p-3 rounded-xl shadow-md transition">
                  <Send className="h-5 w-5" />
                </button>
              </form>
            </div>

            <div className="w-full md:w-[350px] p-6 bg-indigo-50/50 flex flex-col justify-between overflow-y-auto h-1/2 md:h-full">
              <div>
                <h4 className="font-black text-gray-900 text-lg mb-2 flex items-center gap-2">
                  <Sparkles className="h-5 w-5 text-indigo-600" />
                  <span>Real-Time Extraction</span>
                </h4>
                <p className="text-xs text-gray-500 mb-6">Our cognitive NLP model automatically extracts these fields as you chat.</p>

                <div className="space-y-4">
                  <div>
                    <span className="text-xs font-bold text-gray-400 uppercase tracking-wider block mb-1">Detected Name</span>
                    <div className="p-3 bg-white border border-gray-100 rounded-xl text-sm font-bold text-gray-800 shadow-inner">
                      {extractedData.name || <span className="text-gray-300 font-medium italic">Listening...</span>}
                    </div>
                  </div>

                  <div>
                    <span className="text-xs font-bold text-gray-400 uppercase tracking-wider block mb-1">Detected Description</span>
                    <div className="p-3 bg-white border border-gray-100 rounded-xl text-sm font-bold text-gray-800 shadow-inner">
                      {extractedData.description || <span className="text-gray-300 font-medium italic">Listening...</span>}
                    </div>
                  </div>

                  <div>
                    <span className="text-xs font-bold text-gray-400 uppercase tracking-wider block mb-1">Detected Location</span>
                    <div className="p-3 bg-white border border-gray-100 rounded-xl text-sm font-bold text-gray-800 shadow-inner">
                      {extractedData.location || <span className="text-gray-300 font-medium italic">Listening...</span>}
                    </div>
                  </div>

                  <div>
                    <span className="text-xs font-bold text-gray-400 uppercase tracking-wider block mb-1">Report Type</span>
                    <span className={`inline-block px-3 py-1 rounded-full text-xs font-bold mt-1 uppercase ${
                      extractedData.type === 'lost' ? 'bg-rose-100 text-rose-800' :
                      extractedData.type === 'found' ? 'bg-green-100 text-green-800' : 'bg-gray-200 text-gray-600'
                    }`}>
                      {extractedData.type}
                    </span>
                  </div>
                </div>
              </div>

              <button 
                onClick={handlePublishAssistantDraft}
                disabled={!extractedData.name || !extractedData.location}
                className="w-full py-4 mt-6 bg-indigo-600 hover:bg-indigo-700 disabled:bg-gray-300 text-white font-black rounded-2xl transition shadow-lg flex items-center justify-center gap-2"
              >
                <Check className="h-5 w-5" /> Publish Drafted Report
              </button>
            </div>

          </div>
        </div>
      )}

      {/* SECURE REGISTER/LOGIN DIALOGUE MODAL */}
      {authModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm animate-fade-in">
          <div className="bg-white rounded-3xl p-8 max-w-md w-full shadow-2xl border border-gray-100 relative animate-scale-up">
            <button onClick={() => setAuthModalOpen(false)} className="absolute top-4 right-4 text-gray-400 hover:text-gray-600">
              <X className="h-6 w-6" />
            </button>

            <div className="flex border-b border-gray-200 mb-6">
              <button 
                onClick={() => setAuthMode('login')}
                className={`flex-1 pb-3 text-lg font-black transition ${authMode === 'login' ? 'text-indigo-600 border-b-2 border-indigo-600' : 'text-gray-400'}`}
              >
                Log In
              </button>
              <button 
                onClick={() => setAuthMode('register')}
                className={`flex-1 pb-3 text-lg font-black transition ${authMode === 'register' ? 'text-indigo-600 border-b-2 border-indigo-600' : 'text-gray-400'}`}
              >
                Sign Up
              </button>
            </div>

            <form onSubmit={handleAuthSubmit} className="space-y-4">
              <div>
                <label className="block text-sm font-bold text-gray-700 mb-1">Username</label>
                <input 
                  type="text" 
                  required 
                  value={authUsername} 
                  onChange={(e) => setAuthUsername(e.target.value)} 
                  placeholder="yourname"
                  className="w-full p-3 border border-gray-200 rounded-xl bg-gray-50 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                />
              </div>

              {authMode === 'register' && (
                <div>
                  <label className="block text-sm font-bold text-gray-700 mb-1">Email</label>
                  <input 
                    type="email" 
                    value={authEmail} 
                    onChange={(e) => setAuthEmail(e.target.value)} 
                    placeholder="you@example.com"
                    className="w-full p-3 border border-gray-200 rounded-xl bg-gray-50 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  />
                </div>
              )}

              <div>
                <label className="block text-sm font-bold text-gray-700 mb-1">Password</label>
                <input 
                  type="password" 
                  required 
                  value={authPassword} 
                  onChange={(e) => setAuthPassword(e.target.value)} 
                  placeholder="••••••••"
                  className="w-full p-3 border border-gray-200 rounded-xl bg-gray-50 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                />
              </div>

              <button type="submit" className="w-full py-4 bg-indigo-600 hover:bg-indigo-700 text-white font-bold rounded-xl mt-6 shadow-md transition-all">
                {authMode === 'login' ? 'Welcome Back!' : 'Get Started'}
              </button>
            </form>
          </div>
        </div>
      )}

    </div>
  );
}