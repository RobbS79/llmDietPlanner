import React, { useState, useEffect } from 'react';
import { 
  ShoppingCart, 
  Loader2, 
  CheckCircle2, 
  AlertCircle, 
  Sparkles,
  MapPin,
  Utensils,
  Search,
  Check,
  FileText,
  Calculator,
  Wand2,
  ChevronRight
} from 'lucide-react';

/**
 * Integrated App.js with Gemini AI Features
 * Features: 
 * - ✨ Refine Goal (LLM Text expansion)
 * - ✨ Bio-Analysis (LLM calculations)
 */
const App = () => {
  const apiKey = ""; // Provided by environment at runtime

  const [formData, setFormData] = useState({
    sex: 'female',
    age: '',
    weight: '',
    targetWeight: '',
    height: '',
    location: '',
    nutritionGoal: '', 
    mainCourses: ['Breakfast', 'Lunch', 'Dinner'],
    smallMeals: ['Morning Snack', 'Afternoon Snack'],
    smallSnacks: [],
  });

  const [locationSuggestions, setLocationSuggestions] = useState([]);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [isGenerating, setIsGenerating] = useState(false);
  const [generatedContent, setGeneratedContent] = useState(null);
  const [isCheckingOut, setIsCheckingOut] = useState(false);
  const [checkoutError, setCheckoutError] = useState(null);
  const [checkoutSuccess, setCheckoutSuccess] = useState(false);
  
  // Gemini AI State
  const [isRefining, setIsRefining] = useState(false);
  const [aiAnalysis, setAiAnalysis] = useState(null);
  const [isAnalyzing, setIsAnalyzing] = useState(false);

  // Helper for Gemini API calls with exponential backoff
  const callGemini = async (prompt, systemInstruction = "") => {
    const url = `https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-09-2025:generateContent?key=${apiKey}`;
    
    const payload = {
      contents: [{ parts: [{ text: prompt }] }],
      systemInstruction: { parts: [{ text: systemInstruction }] }
    };

    let delay = 1000;
    for (let i = 0; i < 5; i++) {
      try {
        const response = await fetch(url, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
        if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
        const result = await response.json();
        return result.candidates?.[0]?.content?.parts?.[0]?.text;
      } catch (error) {
        if (i === 4) throw error;
        await new Promise(resolve => setTimeout(resolve, delay));
        delay *= 2;
      }
    }
  };

  // ✨ Feature 1: Refine Nutrition Goal
  const refineNutritionGoal = async () => {
    if (!formData.nutritionGoal || formData.nutritionGoal.length < 10) {
      alert("Prosím napište alespoň pár slov o svém cíli.");
      return;
    }
    setIsRefining(true);
    try {
      const refined = await callGemini(
        `User Input: "${formData.nutritionGoal}"`,
        "You are a professional nutritionist. Take the user's rough notes and expand them into a detailed, professional nutrition goal. Keep it in the same language as the input (Czech/Slovak). Focus on specific caloric needs, macro preferences, and health optimization. Be concise but thorough."
      );
      if (refined) {
        setFormData(prev => ({ ...prev, nutritionGoal: refined.trim() }));
      }
    } catch (err) {
      console.error(err);
    } finally {
      setIsRefining(false);
    }
  };

  // ✨ Feature 2: Instant AI Bio-Analysis
  useEffect(() => {
    const timer = setTimeout(async () => {
      if (formData.age && formData.weight && formData.height && formData.sex) {
        setIsAnalyzing(true);
        try {
          const analysis = await callGemini(
            `Data: Sex: ${formData.sex}, Age: ${formData.age}, Weight: ${formData.weight}kg, Height: ${formData.height}cm, Target: ${formData.targetWeight}kg`,
            "Calculate Estimated TDEE and target calories for this person. Return a very short summary in Czech/Slovak like: 'Odhadovaný TDEE: 2400 kcal. Cíl pro hubnutí: 1900 kcal. Doporučené bílkoviny: 140g.'"
          );
          setAiAnalysis(analysis);
        } catch (err) {
          console.error(err);
        } finally {
          setIsAnalyzing(false);
        }
      }
    }, 1500);
    return () => clearTimeout(timer);
  }, [formData.age, formData.weight, formData.height, formData.sex, formData.targetWeight]);

  const handleLocationChange = (e) => {
    const value = e.target.value;
    setFormData({ ...formData, location: value });
    if (value.length > 2) {
      const mockDb = ["Praha", "Brno", "Ostrava", "Bratislava", "Košice", "Plzeň", "Liberec", "Olomouc"];
      const filtered = mockDb.filter(loc => loc.toLowerCase().includes(value.toLowerCase()));
      setLocationSuggestions(filtered);
      setShowSuggestions(true);
    } else {
      setShowSuggestions(false);
    }
  };

  const selectLocation = (loc) => {
    setFormData({ ...formData, location: loc });
    setShowSuggestions(false);
  };

  const toggleMeal = (category, item) => {
    setFormData(prev => {
      const current = prev[category];
      const next = current.includes(item) ? current.filter(i => i !== item) : [...current, item];
      return { ...prev, [category]: next };
    });
  };

  const handleInputChange = (e) => {
    const { name, value } = e.target;
    setFormData(prev => ({ ...prev, [name]: value }));
  };

  const handleGenerate = async () => {
    if (!formData.age || !formData.weight || !formData.height || !formData.location || !formData.nutritionGoal) {
      alert("Prosím vyplňte všechna pole.");
      return;
    }
    setIsGenerating(true);
    try {
      const preview = await callGemini(
        `Biometrics: ${formData.age}y, ${formData.weight}kg, ${formData.sex}. Location: ${formData.location}. Goal: ${formData.nutritionGoal}`,
        "Generate a 2-sentence preview of a meal plan strategy in Czech. Mention one specific meal idea and a macro focus."
      );
      setGeneratedContent(preview);
    } catch (err) {
      setGeneratedContent("Plán byl vygenerován a je připraven k objednání.");
    } finally {
      setIsGenerating(false);
    }
  };

  const handleCheckout = async () => {
    setIsCheckingOut(true);
    try {
      const response = await fetch('/api/shopify/checkout/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          variant_ids: ["gid://shopify/ProductVariant/123456789"], 
          quantities: [1],
          metadata: { ...formData, ai_analysis_preview: aiAnalysis }
        }),
      });
      const result = await response.json();
      if (result.status === 'success' && result.data.checkout_url) {
        setCheckoutSuccess(true);
        window.location.href = result.data.checkout_url;
      }
    } catch (err) {
      setCheckoutError("Chyba při inicializaci platby.");
    } finally {
      setIsCheckingOut(false);
    }
  };

  return (
    <div className="min-h-screen bg-gray-50 py-6 px-4 font-sans text-slate-900">
      <div className="max-w-3xl mx-auto bg-white rounded-[2.5rem] shadow-2xl overflow-hidden border border-gray-100">
        
        <div className="bg-slate-900 p-8 text-white text-center">
          <h1 className="text-3xl font-black tracking-tighter uppercase">MEALPREP <span className="text-blue-400">AI ✨</span></h1>
          <p className="text-slate-400 text-xs mt-1 uppercase tracking-widest font-bold">Personal Nutrition Intelligence</p>
        </div>

        <div className="p-6 md:p-10 space-y-8">
          
          {/* Section: Basic Info */}
          <div className="grid md:grid-cols-2 gap-6">
            <div className="space-y-2">
              <label className="text-[10px] font-black uppercase text-slate-400 tracking-wider">Pohlaví (Sex)</label>
              <div className="flex bg-gray-100 p-1 rounded-2xl">
                {['female', 'male'].map((s) => (
                  <button
                    key={s}
                    onClick={() => setFormData({ ...formData, sex: s })}
                    className={`flex-1 py-2 rounded-xl text-xs font-bold transition-all ${
                      formData.sex === s ? 'bg-white shadow-md text-blue-600' : 'text-slate-400 hover:text-slate-600'
                    }`}
                  >
                    {s === 'female' ? 'Žena' : 'Muž'}
                  </button>
                ))}
              </div>
            </div>

            <div className="space-y-2 relative">
              <label className="text-[10px] font-black uppercase text-slate-400 tracking-wider">Lokalita (CZ/SK)</label>
              <div className="relative">
                <Search className="absolute left-3.5 top-2.5 w-3.5 h-3.5 text-slate-400" />
                <input 
                  name="location" value={formData.location} onChange={handleLocationChange}
                  className="w-full pl-9 pr-4 py-2 bg-gray-100 rounded-xl outline-none focus:ring-2 focus:ring-blue-500 text-xs font-bold"
                  placeholder="Město..."
                />
              </div>
              {showSuggestions && locationSuggestions.length > 0 && (
                <div className="absolute z-20 w-full mt-1 bg-white border border-gray-100 rounded-xl shadow-xl max-h-40 overflow-y-auto">
                  {locationSuggestions.map((loc, i) => (
                    <button key={i} onClick={() => selectLocation(loc)} className="w-full text-left px-4 py-2 text-xs font-medium hover:bg-blue-50 border-b last:border-0 border-gray-50">{loc}</button>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* Section: Biometrics & AI Preview */}
          <div className="space-y-4">
            <div className="bg-gray-50 p-6 rounded-[2rem] border border-gray-100 grid grid-cols-2 md:grid-cols-4 gap-4">
              {[
                { label: 'Věk', name: 'age', unit: 'let' },
                { label: 'Váha', name: 'weight', unit: 'kg' },
                { label: 'Cíl', name: 'targetWeight', unit: 'kg' },
                { label: 'Výška', name: 'height', unit: 'cm' }
              ].map((field) => (
                <div key={field.name} className="space-y-1">
                  <label className="text-[10px] font-black uppercase text-slate-400 text-center block">{field.label}</label>
                  <input 
                    type="number" name={field.name} value={formData[field.name]} onChange={handleInputChange}
                    className="w-full p-2.5 bg-white border border-gray-200 rounded-xl text-center font-black text-slate-700 outline-none focus:border-blue-500 text-sm"
                    placeholder={field.unit}
                  />
                </div>
              ))}
            </div>

            {/* ✨ AI Bio-Analysis Display */}
            {(isAnalyzing || aiAnalysis) && (
              <div className="bg-blue-50 border border-blue-100 p-4 rounded-2xl flex items-start gap-3 animate-in fade-in slide-in-from-top-2">
                <div className="bg-blue-600 p-2 rounded-lg mt-0.5">
                  <Calculator className="w-4 h-4 text-white" />
                </div>
                <div>
                  <h4 className="text-[10px] font-black text-blue-600 uppercase tracking-widest">✨ AI Bio-Analýza</h4>
                  {isAnalyzing ? (
                    <div className="flex items-center gap-2 mt-1">
                      <Loader2 className="w-3 h-3 animate-spin text-blue-400" />
                      <span className="text-xs text-blue-400 italic">Analyzuji metriky...</span>
                    </div>
                  ) : (
                    <p className="text-xs text-blue-900 font-bold mt-1 leading-relaxed">{aiAnalysis}</p>
                  )}
                </div>
              </div>
            )}
          </div>

          {/* Section: Goal with AI Refinement */}
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <label className="text-[10px] font-black uppercase text-slate-400 tracking-wider flex items-center gap-2">
                <FileText className="w-3 h-3" /> Nutriční cíle a požadavky
              </label>
              <button 
                onClick={refineNutritionGoal}
                disabled={isRefining || !formData.nutritionGoal}
                className="flex items-center gap-1.5 text-[10px] font-black text-blue-600 uppercase hover:text-blue-700 disabled:opacity-30 transition-all bg-blue-50 px-3 py-1.5 rounded-full"
              >
                {isRefining ? <Loader2 className="w-3 h-3 animate-spin" /> : <Wand2 className="w-3 h-3" />}
                ✨ Vylepšit cíle AI
              </button>
            </div>
            <textarea 
              name="nutritionGoal" value={formData.nutritionGoal} onChange={handleInputChange}
              className="w-full min-h-[120px] p-5 bg-gray-50 rounded-[2rem] border-2 border-gray-100 outline-none focus:border-blue-500 text-sm font-medium transition-all"
              placeholder="Např.: Chci zhubnout 5kg, miluji asijskou kuchyni, ale nesmím lepek..."
            />
          </div>

          {/* Section: Meal Split */}
          <div className="space-y-4">
            <h3 className="text-[10px] font-black uppercase text-slate-400 tracking-wider flex items-center gap-2">
              <Utensils className="w-3.5 h-3.5" /> Konfigurace Jídelníčku
            </h3>
            <div className="grid gap-4">
              <div className="flex flex-wrap gap-2">
                {['Breakfast', 'Lunch', 'Dinner'].map(meal => (
                  <button key={meal} onClick={() => toggleMeal('mainCourses', meal)}
                    className={`px-4 py-2 rounded-xl text-[10px] font-bold border-2 transition-all flex items-center gap-2 ${
                      formData.mainCourses.includes(meal) ? 'border-blue-600 bg-blue-600 text-white shadow-lg shadow-blue-50' : 'border-gray-100 bg-gray-50 text-slate-400'
                    }`}
                  >
                    {formData.mainCourses.includes(meal) && <Check className="w-3 h-3" />}
                    {meal === 'Breakfast' ? 'Snídaně' : meal === 'Lunch' ? 'Oběd' : 'Večeře'}
                  </button>
                ))}
              </div>
              <div className="flex flex-wrap gap-2">
                {['Morning Snack', 'Afternoon Snack', 'Small Snack 1'].map(meal => (
                  <button key={meal} onClick={() => toggleMeal('smallMeals', meal)}
                    className={`px-4 py-2 rounded-xl text-[10px] font-bold border-2 transition-all ${
                      formData.smallMeals.includes(meal) ? 'border-blue-500 bg-blue-500 text-white' : 'border-gray-100 bg-gray-50 text-slate-400'
                    }`}
                  >
                    {meal === 'Morning Snack' ? 'Svačina dop.' : meal === 'Afternoon Snack' ? 'Svačina odp.' : 'Snack'}
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* Actions */}
          <div className="pt-4 space-y-4">
            <button
              onClick={handleGenerate}
              disabled={isGenerating}
              className="w-full py-4 bg-slate-900 text-white rounded-2xl font-black text-lg hover:bg-slate-800 transition-all flex items-center justify-center gap-3 disabled:opacity-50 shadow-xl"
            >
              {isGenerating ? <Loader2 className="animate-spin w-5 h-5" /> : <><Sparkles className="w-5 h-5 text-blue-400" /> ✨ VYGENEROVAT NÁHLED PLÁNU</>}
            </button>

            {generatedContent && (
              <div className="animate-in fade-in zoom-in duration-500 border-4 border-blue-500 rounded-[2rem] p-8 bg-blue-50 flex flex-col items-center shadow-inner">
                <div className="bg-blue-600 p-2 rounded-full mb-4 shadow-lg"><CheckCircle2 className="w-6 h-6 text-white" /></div>
                <p className="text-center text-blue-900 text-lg font-bold italic mb-8">"{generatedContent}"</p>
                <button onClick={handleCheckout} disabled={isCheckingOut || checkoutSuccess}
                  className={`w-full py-5 rounded-[1.5rem] font-black text-2xl transition-all shadow-2xl transform active:scale-95 ${
                    checkoutSuccess ? 'bg-green-500 text-white' : 'bg-blue-600 hover:bg-blue-700 text-white shadow-blue-200'
                  }`}
                >
                  {isCheckingOut ? <Loader2 className="animate-spin w-8 h-8" /> : checkoutSuccess ? "ÚSPĚCH!" : (
                    <div className="flex flex-col items-center">
                      <div className="flex items-center gap-3"><ShoppingCart className="w-7 h-7" /> OBJEDNAT PLNÝ PLÁN</div>
                      <span className="text-[10px] opacity-60 uppercase mt-1 tracking-widest font-black">Zabezpečený checkout</span>
                    </div>
                  )}
                </button>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default App;