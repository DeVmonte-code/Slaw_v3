import React, { useState, useMemo, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { ChevronRight, ArrowLeft, CheckCircle2, Building2, User, Home, Briefcase, MapPin, Calculator, ShieldCheck } from "lucide-react";

const CANTONS = [
  "AG", "AI", "AR", "BE", "BL", "BS", "FR", "GE", "GL", "GR", "JU", "LU",
  "NE", "NW", "OW", "SG", "SH", "SO", "SZ", "TG", "TI", "UR", "VD", "VS", "ZG", "ZH"
];

const EMPLOYMENT_OPTIONS = [
  { value: "employee_full_time", label: "Employee (full-time)" },
  { value: "employee_part_time", label: "Employee (part-time)" },
  { value: "self_employed", label: "Self-employed" },
  { value: "business_owner", label: "Business owner" },
  { value: "unemployed", label: "Unemployed" },
  { value: "student", label: "Student" },
  { value: "retired", label: "Retired" },
];

const HOUSING_OPTIONS = [
  { value: "tenant", label: "Tenant" },
  { value: "owner", label: "Owner" },
  { value: "living_with_family", label: "Living with family" },
];

const MARITAL_OPTIONS = [
  { value: "single", label: "Single" },
  { value: "married", label: "Married" },
  { value: "registered_partnership", label: "Registered partnership" },
  { value: "divorced", label: "Divorced" },
  { value: "widowed", label: "Widowed" },
];

const INCOME_OPTIONS = [
  { value: "lt_30k", label: "Under CHF 30,000" },
  { value: "30_50k", label: "CHF 30,000–50,000" },
  { value: "50_80k", label: "CHF 50,000–80,000" },
  { value: "80_120k", label: "CHF 80,000–120,000" },
  { value: "120_200k", label: "CHF 120,000–200,000" },
  { value: "gt_200k", label: "Over CHF 200,000" },
];

type AppState = {
  canton: string;
  employment_status: string;
  employment_start_year: string;
  weekly_hours: string;
  commute_km_daily: string;
  housing_status: string;
  rental_start_year: string;
  rent_chf_monthly: string;
  lease_reference_rate_tracked: boolean | null;
  marital_status: string;
  household_size: string;
  children_count: string;
  childcare_cost_chf_yearly: string;
  income_band_chf: string;
  has_third_pillar: boolean | null;
  third_pillar_chf_this_year: string;
};

const DEFAULT_STATE: AppState = {
  canton: "",
  employment_status: "",
  employment_start_year: "",
  weekly_hours: "",
  commute_km_daily: "",
  housing_status: "",
  rental_start_year: "",
  rent_chf_monthly: "",
  lease_reference_rate_tracked: null,
  marital_status: "",
  household_size: "",
  children_count: "",
  childcare_cost_chf_yearly: "",
  income_band_chf: "",
  has_third_pillar: null,
  third_pillar_chf_this_year: "",
};

type StepDef = {
  id: keyof AppState | "intro" | "processing" | "done";
  title?: string;
  subtitle?: string;
  condition?: (state: AppState) => boolean;
  render?: (state: AppState, update: (vals: Partial<AppState>) => void, next: () => void, handleKeydown: (e: React.KeyboardEvent) => void) => React.ReactNode;
};

const AnimatedLayout = ({ children, direction }: { children: React.ReactNode, direction: number }) => (
  <motion.div
    key={React.isValidElement(children) ? children.key : "content"}
    initial={{ opacity: 0, x: direction > 0 ? 30 : -30, y: 10 }}
    animate={{ opacity: 1, x: 0, y: 0 }}
    exit={{ opacity: 0, x: direction > 0 ? -30 : 30, y: -10 }}
    transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
    className="w-full max-w-2xl mx-auto"
  >
    {children}
  </motion.div>
);

const OptionButton = ({ 
  selected, 
  onClick, 
  children,
  icon: Icon
}: { 
  selected: boolean; 
  onClick: () => void; 
  children: React.ReactNode;
  icon?: any;
}) => (
  <button
    onClick={onClick}
    className={`w-full text-left px-6 py-4 rounded-xl border transition-all duration-200 flex items-center justify-between group ${
      selected 
        ? "border-[#047857] bg-[#ecfdf5] shadow-sm" 
        : "border-gray-200 hover:border-[#047857]/50 hover:bg-gray-50 bg-white"
    }`}
  >
    <div className="flex items-center gap-4">
      {Icon && (
        <div className={`p-2 rounded-lg ${selected ? "bg-[#047857] text-white" : "bg-gray-100 text-gray-500 group-hover:bg-[#ecfdf5] group-hover:text-[#047857]"}`}>
          <Icon className="w-5 h-5" />
        </div>
      )}
      <span className={`text-lg ${selected ? "text-[#047857] font-medium" : "text-gray-700"}`}>
        {children}
      </span>
    </div>
    <div className={`w-6 h-6 rounded-full border-2 flex items-center justify-center transition-colors ${
      selected ? "border-[#047857] bg-[#047857]" : "border-gray-300"
    }`}>
      {selected && <CheckCircle2 className="w-4 h-4 text-white" />}
    </div>
  </button>
);

const TextInput = ({ 
  value, 
  onChange, 
  placeholder, 
  type = "text",
  suffix,
  onKeyDown,
  autoFocus = true
}: { 
  value: string; 
  onChange: (v: string) => void; 
  placeholder?: string; 
  type?: string;
  suffix?: string;
  onKeyDown?: (e: React.KeyboardEvent) => void;
  autoFocus?: boolean;
}) => (
  <div className="relative flex items-center">
    <input
      type={type}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      onKeyDown={onKeyDown}
      placeholder={placeholder}
      autoFocus={autoFocus}
      className="w-full text-2xl px-0 py-4 bg-transparent border-0 border-b-2 border-gray-200 focus:border-[#047857] focus:ring-0 transition-colors placeholder:text-gray-300 text-gray-800 outline-none"
    />
    {suffix && (
      <span className="absolute right-0 text-xl text-gray-400 pointer-events-none">
        {suffix}
      </span>
    )}
  </div>
);

export default function SmartInterview() {
  const [state, setState] = useState<AppState>(DEFAULT_STATE);
  const [stepIndex, setStepIndex] = useState(0);
  const [direction, setDirection] = useState(1);
  const [isProcessing, setIsProcessing] = useState(false);

  const updateState = (vals: Partial<AppState>) => {
    setState((prev) => ({ ...prev, ...vals }));
  };

  const steps: StepDef[] = useMemo(() => [
    {
      id: "intro",
      render: (_, __, next) => (
        <div key="intro" className="text-center py-12">
          <div className="w-20 h-20 bg-[#ecfdf5] rounded-full flex items-center justify-center mx-auto mb-8">
            <ShieldCheck className="w-10 h-10 text-[#047857]" />
          </div>
          <h1 className="text-4xl font-semibold text-gray-900 mb-4 tracking-tight">
            Discover your Swiss legal rights
          </h1>
          <p className="text-xl text-gray-500 mb-12 max-w-lg mx-auto leading-relaxed">
            We'll ask a few questions to tailor your personalized scan of rights, deductions, and protections. It takes about 2 minutes.
          </p>
          <button
            onClick={next}
            className="inline-flex items-center gap-2 bg-[#047857] text-white px-8 py-4 rounded-full text-lg font-medium hover:bg-[#065f46] transition-colors shadow-sm hover:shadow-md cursor-pointer outline-none"
          >
            Start Assessment
            <ChevronRight className="w-5 h-5" />
          </button>
        </div>
      )
    },
    {
      id: "canton",
      title: "Where do you live?",
      subtitle: "Laws and tax deductions vary significantly by canton.",
      render: (s, u, next) => (
        <div key="canton" className="space-y-6">
          <div className="relative">
            <MapPin className="absolute left-4 top-1/2 -translate-y-1/2 text-gray-400 w-6 h-6 pointer-events-none" />
            <select
              value={s.canton}
              onChange={(e) => {
                u({ canton: e.target.value });
                setTimeout(next, 300);
              }}
              className="w-full text-2xl pl-14 pr-6 py-5 bg-white border-2 border-gray-200 rounded-2xl focus:border-[#047857] focus:ring-0 appearance-none shadow-sm cursor-pointer hover:border-gray-300 transition-colors text-gray-800 outline-none"
            >
              <option value="" disabled>Select your canton...</option>
              {CANTONS.map(c => <option key={c} value={c}>{c}</option>)}
            </select>
          </div>
        </div>
      )
    },
    {
      id: "employment_status",
      title: "What is your current employment status?",
      subtitle: "This determines which labor laws and tax rules apply to you.",
      render: (s, u, next) => (
        <div key="emp_stat" className="grid gap-3">
          {EMPLOYMENT_OPTIONS.map(opt => (
            <OptionButton
              key={opt.value}
              icon={Briefcase}
              selected={s.employment_status === opt.value}
              onClick={() => {
                u({ employment_status: opt.value });
                setTimeout(next, 300);
              }}
            >
              {opt.label}
            </OptionButton>
          ))}
        </div>
      )
    },
    {
      id: "employment_start_year",
      title: "In what year did you start your current work?",
      subtitle: "Used to calculate notice periods and tenure-based rights.",
      render: (s, u, next, onKey) => (
        <div key="emp_year" className="space-y-8">
          <TextInput 
            type="number"
            value={s.employment_start_year} 
            onChange={(v) => u({ employment_start_year: v })} 
            placeholder="e.g. 2018"
            onKeyDown={onKey}
          />
          <button 
            onClick={next} 
            disabled={!s.employment_start_year}
            className="bg-[#047857] text-white px-8 py-3 rounded-full font-medium hover:bg-[#065f46] disabled:opacity-30 disabled:cursor-not-allowed transition-all outline-none"
          >
            Continue
          </button>
        </div>
      )
    },
    {
      id: "weekly_hours",
      title: "How many hours do you work per week?",
      render: (s, u, next, onKey) => (
        <div key="hours" className="space-y-8">
          <TextInput 
            type="number"
            value={s.weekly_hours} 
            onChange={(v) => u({ weekly_hours: v })} 
            placeholder="e.g. 42"
            suffix="hours"
            onKeyDown={onKey}
          />
          <button 
            onClick={next} 
            disabled={!s.weekly_hours}
            className="bg-[#047857] text-white px-8 py-3 rounded-full font-medium hover:bg-[#065f46] disabled:opacity-30 disabled:cursor-not-allowed transition-all outline-none"
          >
            Continue
          </button>
        </div>
      )
    },
    {
      id: "commute_km_daily",
      title: "What is your daily commute distance?",
      subtitle: "You may be eligible for transport tax deductions.",
      render: (s, u, next, onKey) => (
        <div key="commute" className="space-y-8">
          <TextInput 
            type="number"
            value={s.commute_km_daily} 
            onChange={(v) => u({ commute_km_daily: v })} 
            placeholder="e.g. 12"
            suffix="km (round trip)"
            onKeyDown={onKey}
          />
          <button 
            onClick={next} 
            disabled={!s.commute_km_daily}
            className="bg-[#047857] text-white px-8 py-3 rounded-full font-medium hover:bg-[#065f46] disabled:opacity-30 disabled:cursor-not-allowed transition-all outline-none"
          >
            Continue
          </button>
        </div>
      )
    },
    {
      id: "housing_status",
      title: "What is your living situation?",
      subtitle: "Tenant protections differ significantly from homeownership rules.",
      render: (s, u, next) => (
        <div key="housing" className="grid gap-3">
          {HOUSING_OPTIONS.map(opt => (
            <OptionButton
              key={opt.value}
              icon={opt.value === 'tenant' ? Building2 : Home}
              selected={s.housing_status === opt.value}
              onClick={() => {
                u({ housing_status: opt.value });
                setTimeout(next, 300);
              }}
            >
              {opt.label}
            </OptionButton>
          ))}
        </div>
      )
    },
    {
      id: "rental_start_year",
      condition: (s) => s.housing_status === "tenant",
      title: "What year did your current lease start?",
      render: (s, u, next, onKey) => (
        <div key="rent_year" className="space-y-8">
          <TextInput 
            type="number"
            value={s.rental_start_year} 
            onChange={(v) => u({ rental_start_year: v })} 
            placeholder="e.g. 2020"
            onKeyDown={onKey}
          />
          <button 
            onClick={next} 
            disabled={!s.rental_start_year}
            className="bg-[#047857] text-white px-8 py-3 rounded-full font-medium hover:bg-[#065f46] disabled:opacity-30 disabled:cursor-not-allowed transition-all outline-none"
          >
            Continue
          </button>
        </div>
      )
    },
    {
      id: "rent_chf_monthly",
      condition: (s) => s.housing_status === "tenant",
      title: "What is your monthly rent?",
      subtitle: "Including ancillary costs.",
      render: (s, u, next, onKey) => (
        <div key="rent_amt" className="space-y-8">
          <TextInput 
            type="number"
            value={s.rent_chf_monthly} 
            onChange={(v) => u({ rent_chf_monthly: v })} 
            placeholder="e.g. 2400"
            suffix="CHF"
            onKeyDown={onKey}
          />
          <button 
            onClick={next} 
            disabled={!s.rent_chf_monthly}
            className="bg-[#047857] text-white px-8 py-3 rounded-full font-medium hover:bg-[#065f46] disabled:opacity-30 disabled:cursor-not-allowed transition-all outline-none"
          >
            Continue
          </button>
        </div>
      )
    },
    {
      id: "lease_reference_rate_tracked",
      condition: (s) => s.housing_status === "tenant",
      title: "Is your rent tied to the official reference interest rate?",
      subtitle: "Most Swiss leases are. If yes, you might be entitled to a rent reduction.",
      render: (s, u, next) => (
        <div key="ref_rate" className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <OptionButton
            selected={s.lease_reference_rate_tracked === true}
            onClick={() => {
              u({ lease_reference_rate_tracked: true });
              setTimeout(next, 300);
            }}
          >
            Yes, it is
          </OptionButton>
          <OptionButton
            selected={s.lease_reference_rate_tracked === false}
            onClick={() => {
              u({ lease_reference_rate_tracked: false });
              setTimeout(next, 300);
            }}
          >
            No / Not sure
          </OptionButton>
        </div>
      )
    },
    {
      id: "marital_status",
      title: "What is your marital status?",
      subtitle: "Crucial for determining tax brackets and family law rights.",
      render: (s, u, next) => (
        <div key="marital" className="grid gap-3">
          {MARITAL_OPTIONS.map(opt => (
            <OptionButton
              key={opt.value}
              icon={User}
              selected={s.marital_status === opt.value}
              onClick={() => {
                u({ marital_status: opt.value });
                setTimeout(next, 300);
              }}
            >
              {opt.label}
            </OptionButton>
          ))}
        </div>
      )
    },
    {
      id: "household_size",
      title: "How many people live in your household?",
      subtitle: "Include yourself, partner, children, and any other residents.",
      render: (s, u, next, onKey) => (
        <div key="hh_size" className="space-y-8">
          <TextInput 
            type="number"
            value={s.household_size} 
            onChange={(v) => u({ household_size: v })} 
            placeholder="e.g. 4"
            onKeyDown={onKey}
          />
          <button 
            onClick={next} 
            disabled={!s.household_size}
            className="bg-[#047857] text-white px-8 py-3 rounded-full font-medium hover:bg-[#065f46] disabled:opacity-30 disabled:cursor-not-allowed transition-all outline-none"
          >
            Continue
          </button>
        </div>
      )
    },
    {
      id: "children_count",
      title: "How many dependent children do you have?",
      render: (s, u, next, onKey) => (
        <div key="kids" className="space-y-8">
          <TextInput 
            type="number"
            value={s.children_count} 
            onChange={(v) => u({ children_count: v })} 
            placeholder="e.g. 2"
            onKeyDown={onKey}
          />
          <button 
            onClick={next} 
            disabled={!s.children_count}
            className="bg-[#047857] text-white px-8 py-3 rounded-full font-medium hover:bg-[#065f46] disabled:opacity-30 disabled:cursor-not-allowed transition-all outline-none"
          >
            Continue
          </button>
        </div>
      )
    },
    {
      id: "childcare_cost_chf_yearly",
      condition: (s) => parseInt(s.children_count || "0", 10) > 0,
      title: "What are your estimated yearly childcare costs?",
      subtitle: "Daycare, after-school care, or childminders (CHF per year).",
      render: (s, u, next, onKey) => (
        <div key="childcare" className="space-y-8">
          <TextInput 
            type="number"
            value={s.childcare_cost_chf_yearly} 
            onChange={(v) => u({ childcare_cost_chf_yearly: v })} 
            placeholder="e.g. 18000"
            suffix="CHF"
            onKeyDown={onKey}
          />
          <button 
            onClick={next} 
            disabled={!s.childcare_cost_chf_yearly}
            className="bg-[#047857] text-white px-8 py-3 rounded-full font-medium hover:bg-[#065f46] disabled:opacity-30 disabled:cursor-not-allowed transition-all outline-none"
          >
            Continue
          </button>
        </div>
      )
    },
    {
      id: "income_band_chf",
      title: "What is your approximate gross household income?",
      subtitle: "We use this to estimate tax bracket implications.",
      render: (s, u, next) => (
        <div key="income" className="grid gap-3 sm:grid-cols-2">
          {INCOME_OPTIONS.map(opt => (
            <OptionButton
              key={opt.value}
              selected={s.income_band_chf === opt.value}
              onClick={() => {
                u({ income_band_chf: opt.value });
                setTimeout(next, 300);
              }}
            >
              {opt.label}
            </OptionButton>
          ))}
        </div>
      )
    },
    {
      id: "has_third_pillar",
      title: "Do you contribute to a 3rd Pillar (Pillar 3a) account?",
      render: (s, u, next) => (
        <div key="p3_bool" className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <OptionButton
            selected={s.has_third_pillar === true}
            onClick={() => {
              u({ has_third_pillar: true });
              setTimeout(next, 300);
            }}
          >
            Yes, I do
          </OptionButton>
          <OptionButton
            selected={s.has_third_pillar === false}
            onClick={() => {
              u({ has_third_pillar: false });
              setTimeout(next, 300);
            }}
          >
            No, I don't
          </OptionButton>
        </div>
      )
    },
    {
      id: "third_pillar_chf_this_year",
      condition: (s) => s.has_third_pillar === true,
      title: "How much will you contribute to your 3a account this year?",
      subtitle: "The legal maximum is generally CHF 7,056 for employees.",
      render: (s, u, next, onKey) => (
        <div key="p3_amt" className="space-y-8">
          <TextInput 
            type="number"
            value={s.third_pillar_chf_this_year} 
            onChange={(v) => u({ third_pillar_chf_this_year: v })} 
            placeholder="e.g. 7056"
            suffix="CHF"
            onKeyDown={onKey}
          />
          <button 
            onClick={next} 
            disabled={!s.third_pillar_chf_this_year}
            className="bg-[#047857] text-white px-8 py-3 rounded-full font-medium hover:bg-[#065f46] disabled:opacity-30 disabled:cursor-not-allowed transition-all outline-none"
          >
            Continue
          </button>
        </div>
      )
    }
  ], []);

  const activeSteps = useMemo(() => steps.filter(s => !s.condition || s.condition(state)), [state, steps]);
  const currentStep = activeSteps[stepIndex];

  // If somehow stepIndex is out of bounds (e.g. going back changed conditions), fix it
  useEffect(() => {
    if (stepIndex >= activeSteps.length && activeSteps.length > 0) {
      setStepIndex(activeSteps.length - 1);
    }
  }, [activeSteps, stepIndex]);

  const handleNext = () => {
    if (stepIndex < activeSteps.length - 1) {
      setDirection(1);
      setStepIndex(prev => prev + 1);
    } else {
      setDirection(1);
      setIsProcessing(true);
      setTimeout(() => {
        setIsProcessing(false);
        // would transition to results in real app
        console.log("Submit to backend:", state);
        alert("Scan complete! Check console for payload.");
      }, 2000);
    }
  };

  const handleBack = () => {
    if (stepIndex > 0) {
      setDirection(-1);
      setStepIndex(prev => prev - 1);
    }
  };

  const handleKeydown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") {
      // Find if we have a valid value for the current field
      let canAdvance = false;
      const id = currentStep?.id;
      if (id && id !== "intro") {
        const val = state[id as keyof AppState];
        if (val !== "" && val !== null) {
          canAdvance = true;
        }
      }
      if (canAdvance) {
        handleNext();
      }
    }
  };

  const progress = stepIndex === 0 ? 0 : Math.round(((stepIndex) / (activeSteps.length - 1)) * 100);
  const remaining = activeSteps.length - 1 - stepIndex;

  return (
    <div className="min-h-[100dvh] bg-[#fafaf9] font-sans flex flex-col selection:bg-[#047857] selection:text-white">
      <style dangerouslySetInnerHTML={{__html: `
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600&display=swap');
        * { font-family: 'Inter', sans-serif; }
      `}} />
      
      {/* Header / Nav */}
      <header className="px-6 py-6 flex items-center justify-between z-10 relative">
        <div className="flex items-center gap-2">
          {stepIndex > 0 && !isProcessing && (
            <button 
              onClick={handleBack}
              className="p-2 -ml-2 rounded-full text-gray-500 hover:bg-gray-100 hover:text-gray-900 transition-colors outline-none cursor-pointer"
              aria-label="Go back"
            >
              <ArrowLeft className="w-6 h-6" />
            </button>
          )}
          <span className="font-semibold text-[#047857] tracking-tight ml-2">Slaw</span>
        </div>
        
        {stepIndex > 0 && !isProcessing && (
          <div className="text-sm font-medium text-gray-400">
            {remaining > 0 ? `About ${remaining} question${remaining > 1 ? 's' : ''} left` : 'Final question'}
          </div>
        )}
      </header>

      {/* Progress Bar */}
      {stepIndex > 0 && !isProcessing && (
        <div className="w-full h-1 bg-gray-100 fixed top-0 left-0 z-20">
          <motion.div 
            className="h-full bg-[#047857]"
            initial={{ width: 0 }}
            animate={{ width: `${progress}%` }}
            transition={{ duration: 0.3, ease: "easeInOut" }}
          />
        </div>
      )}

      {/* Main Content Area */}
      <main className="flex-1 flex flex-col items-center justify-center p-6 relative overflow-hidden w-full">
        <AnimatePresence mode="wait" custom={direction}>
          {isProcessing ? (
            <AnimatedLayout key="processing" direction={direction}>
              <div className="text-center py-20">
                <div className="relative w-24 h-24 mx-auto mb-8">
                  <motion.div
                    animate={{ rotate: 360 }}
                    transition={{ duration: 2, repeat: Infinity, ease: "linear" }}
                    className="absolute inset-0 rounded-full border-4 border-gray-100 border-t-[#047857]"
                  />
                  <div className="absolute inset-0 flex items-center justify-center">
                    <Calculator className="w-8 h-8 text-[#047857]" />
                  </div>
                </div>
                <h2 className="text-2xl font-semibold text-gray-900 mb-2">Analyzing your profile</h2>
                <p className="text-gray-500">Checking federal and cantonal regulations...</p>
              </div>
            </AnimatedLayout>
          ) : currentStep ? (
            <AnimatedLayout key={currentStep.id} direction={direction}>
              {currentStep.title && (
                <div className="mb-10">
                  <h2 className="text-3xl sm:text-4xl font-semibold text-gray-900 tracking-tight leading-tight mb-4">
                    {currentStep.title}
                  </h2>
                  {currentStep.subtitle && (
                    <p className="text-xl text-gray-500 leading-relaxed">
                      {currentStep.subtitle}
                    </p>
                  )}
                </div>
              )}
              {currentStep.render?.(state, updateState, handleNext, handleKeydown)}
            </AnimatedLayout>
          ) : null}
        </AnimatePresence>
      </main>

      {/* Footer safe area */}
      <div className="h-12" />
    </div>
  );
}
