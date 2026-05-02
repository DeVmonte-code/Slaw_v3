import React, { useState, useEffect, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Check, Edit2, ArrowRight, MapPin, Briefcase, Home, Users, Wallet, Plus, X } from "lucide-react";
import "./_group.css";
import type { ContextProfile, LifeEvent } from "./types";

const CANTONS = ["AG","AI","AR","BE","BL","BS","FR","GE","GL","GR","JU","LU","NE","NW","OW","SG","SH","SO","SZ","TG","TI","UR","VD","VS","ZG","ZH"];
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

const EVENTS = [
  { value: "moved_canton", label: "Moved canton" },
  { value: "had_child", label: "Had a child" },
  { value: "got_married", label: "Got married" },
  { value: "got_divorced", label: "Got divorced" },
  { value: "lost_job", label: "Lost job" },
  { value: "started_business", label: "Started a business" },
  { value: "started_studies", label: "Started studies" },
  { value: "bought_property", label: "Bought property" },
  { value: "retired", label: "Retired" },
];

type StepId = 
  | "canton"
  | "housing_status"
  | "housing_details"
  | "employment_status"
  | "employment_details"
  | "marital_status"
  | "household"
  | "childcare"
  | "income"
  | "pillar3"
  | "life_events"
  | "done";

type ProfileData = ContextProfile;

const DEFAULT_PROFILE: ProfileData = {
  canton: "ZH",
  employment_status: "employee_full_time",
  employment_start_year: 2018,
  weekly_hours: 42,
  commute_km_daily: 12,
  housing_status: "tenant",
  rental_start_year: 2018,
  lease_reference_rate_tracked: true,
  rent_chf_monthly: 2400,
  household_size: 4,
  children_count: 2,
  marital_status: "married",
  income_band_chf: "120_200k",
  has_third_pillar: true,
  third_pillar_chf_this_year: 7056,
  childcare_cost_chf_yearly: 18000,
  recent_life_events: [],
};

const STEP_ORDER: StepId[] = [
  "canton",
  "housing_status",
  "housing_details",
  "employment_status",
  "employment_details",
  "marital_status",
  "household",
  "childcare",
  "income",
  "pillar3",
  "life_events",
  "done"
];

function BotBubble({ children, delay = 0 }: { children: React.ReactNode, delay?: number }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 10, scale: 0.95 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ duration: 0.4, delay, ease: "easeOut" }}
      className="flex w-full justify-start mb-4 pr-12"
    >
      <div className="bg-white border border-[var(--slaw-line)] text-[var(--slaw-ink)] rounded-2xl rounded-tl-sm px-4 py-3 shadow-sm text-[15px] leading-relaxed">
        {children}
      </div>
    </motion.div>
  );
}

function UserBubble({ children, onEdit, isEditing }: { children: React.ReactNode, onEdit?: () => void, isEditing?: boolean }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 10, scale: 0.95 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ duration: 0.3, ease: "easeOut" }}
      className="flex w-full justify-end mb-4 pl-12 group"
    >
      <div className="relative">
        <div className="bg-[var(--slaw-primary-strong)] text-white rounded-2xl rounded-tr-sm px-4 py-3 shadow-sm text-[15px] leading-relaxed">
          {children}
        </div>
        {onEdit && !isEditing && (
          <button 
            onClick={onEdit}
            className="absolute -left-10 top-1/2 -translate-y-1/2 p-2 text-[var(--slaw-ink-soft)] opacity-0 group-hover:opacity-100 transition-opacity hover:text-[var(--slaw-primary)]"
            aria-label="Edit answer"
          >
            <Edit2 size={14} />
          </button>
        )}
      </div>
    </motion.div>
  );
}

function Chip({ selected, onClick, children }: { selected: boolean, onClick: () => void, children: React.ReactNode }) {
  return (
    <button
      onClick={onClick}
      className={`px-4 py-2 rounded-full border text-sm font-medium transition-all ${
        selected 
          ? "bg-[var(--slaw-primary-strong)] border-[var(--slaw-primary-strong)] text-white shadow-md" 
          : "bg-white border-[var(--slaw-line-strong)] text-[var(--slaw-ink)] hover:border-[var(--slaw-primary)] hover:bg-[var(--slaw-primary-soft)]"
      }`}
    >
      {children}
    </button>
  );
}

export default function ConversationalChat() {
  const [profile, setProfile] = useState<ProfileData>(DEFAULT_PROFILE);
  const [currentStepIdx, setCurrentStepIdx] = useState(0);
  const [history, setHistory] = useState<{ step: StepId, completed: boolean }[]>([
    { step: "canton", completed: false }
  ]);
  const [isScanning, setIsScanning] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTo({
        top: scrollRef.current.scrollHeight,
        behavior: "smooth"
      });
    }
  }, [history, currentStepIdx]);

  const nextStep = () => {
    const nextIdx = currentStepIdx + 1;
    
    // Skip logic
    let targetIdx = nextIdx;
    if (STEP_ORDER[targetIdx] === "housing_details" && profile.housing_status !== "tenant") {
      targetIdx++;
    }
    if (STEP_ORDER[targetIdx] === "employment_details" && ["unemployed", "student", "retired"].includes(profile.employment_status)) {
      targetIdx++;
    }
    if (STEP_ORDER[targetIdx] === "childcare" && profile.children_count === 0) {
      targetIdx++;
    }

    if (targetIdx < STEP_ORDER.length) {
      setHistory(prev => {
        const newHist = [...prev];
        newHist[newHist.length - 1].completed = true;
        newHist.push({ step: STEP_ORDER[targetIdx], completed: false });
        return newHist;
      });
      setCurrentStepIdx(targetIdx);
    }
  };

  const handleEdit = (idx: number) => {
    setHistory(prev => prev.slice(0, idx + 1).map((h, i) => ({ ...h, completed: i !== idx })));
    setCurrentStepIdx(STEP_ORDER.indexOf(history[idx].step));
  };

  const updateProfile = (updates: Partial<ProfileData>) => {
    setProfile(prev => ({ ...prev, ...updates }));
  };

  const renderActiveInput = (step: StepId) => {
    switch (step) {
      case "canton":
        return (
          <div className="flex flex-wrap gap-2 mt-2">
            {["ZH", "BE", "VD", "GE"].map(c => (
              <Chip key={c} selected={profile.canton === c} onClick={() => { updateProfile({ canton: c }); nextStep(); }}>
                {c}
              </Chip>
            ))}
            <select 
              className="px-4 py-2 rounded-full border border-[var(--slaw-line-strong)] bg-white text-sm font-medium outline-none focus:border-[var(--slaw-primary)]"
              value={profile.canton}
              onChange={(e) => { updateProfile({ canton: e.target.value }); nextStep(); }}
            >
              <option value="" disabled>Other canton...</option>
              {CANTONS.filter(c => !["ZH", "BE", "VD", "GE"].includes(c)).map(c => (
                <option key={c} value={c}>{c}</option>
              ))}
            </select>
          </div>
        );
      
      case "housing_status":
        return (
          <div className="flex flex-wrap gap-2 mt-2">
            {HOUSING_OPTIONS.map(o => (
              <Chip key={o.value} selected={profile.housing_status === o.value} onClick={() => { updateProfile({ housing_status: o.value }); nextStep(); }}>
                {o.label}
              </Chip>
            ))}
          </div>
        );

      case "housing_details":
        return (
          <div className="mt-2 space-y-4 bg-white p-4 rounded-xl border border-[var(--slaw-line)] shadow-sm">
            <div>
              <label className="block text-xs font-semibold text-[var(--slaw-ink-soft)] uppercase tracking-wider mb-1">Monthly Rent (CHF)</label>
              <input type="number" value={profile.rent_chf_monthly || ""} onChange={e => updateProfile({ rent_chf_monthly: Number(e.target.value) })} className="w-full border border-[var(--slaw-line-strong)] rounded-lg px-3 py-2 text-sm outline-none focus:border-[var(--slaw-primary)]" />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-semibold text-[var(--slaw-ink-soft)] uppercase tracking-wider mb-1">Start Year</label>
                <input type="number" value={profile.rental_start_year || ""} onChange={e => updateProfile({ rental_start_year: Number(e.target.value) })} className="w-full border border-[var(--slaw-line-strong)] rounded-lg px-3 py-2 text-sm outline-none focus:border-[var(--slaw-primary)]" />
              </div>
              <div className="flex items-end">
                <label className="flex items-center gap-2 text-sm text-[var(--slaw-ink)] pb-2 cursor-pointer">
                  <input type="checkbox" checked={profile.lease_reference_rate_tracked} onChange={e => updateProfile({ lease_reference_rate_tracked: e.target.checked })} className="accent-[var(--slaw-primary)]" />
                  Reference rate tracked
                </label>
              </div>
            </div>
            <button onClick={nextStep} className="w-full py-2 bg-[var(--slaw-primary-strong)] text-white rounded-lg text-sm font-medium hover:bg-[var(--slaw-primary)] transition-colors">Continue</button>
          </div>
        );

      case "employment_status":
        return (
          <div className="flex flex-wrap gap-2 mt-2">
            {EMPLOYMENT_OPTIONS.map(o => (
              <Chip key={o.value} selected={profile.employment_status === o.value} onClick={() => { updateProfile({ employment_status: o.value }); nextStep(); }}>
                {o.label}
              </Chip>
            ))}
          </div>
        );

      case "employment_details":
        return (
          <div className="mt-2 space-y-4 bg-white p-4 rounded-xl border border-[var(--slaw-line)] shadow-sm">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-semibold text-[var(--slaw-ink-soft)] uppercase tracking-wider mb-1">Start Year</label>
                <input type="number" value={profile.employment_start_year || ""} onChange={e => updateProfile({ employment_start_year: Number(e.target.value) })} className="w-full border border-[var(--slaw-line-strong)] rounded-lg px-3 py-2 text-sm outline-none focus:border-[var(--slaw-primary)]" />
              </div>
              <div>
                <label className="block text-xs font-semibold text-[var(--slaw-ink-soft)] uppercase tracking-wider mb-1">Weekly Hours</label>
                <input type="number" value={profile.weekly_hours || ""} onChange={e => updateProfile({ weekly_hours: Number(e.target.value) })} className="w-full border border-[var(--slaw-line-strong)] rounded-lg px-3 py-2 text-sm outline-none focus:border-[var(--slaw-primary)]" />
              </div>
              <div className="col-span-2">
                <label className="block text-xs font-semibold text-[var(--slaw-ink-soft)] uppercase tracking-wider mb-1">Daily Commute (km)</label>
                <input type="number" value={profile.commute_km_daily || ""} onChange={e => updateProfile({ commute_km_daily: Number(e.target.value) })} className="w-full border border-[var(--slaw-line-strong)] rounded-lg px-3 py-2 text-sm outline-none focus:border-[var(--slaw-primary)]" />
              </div>
            </div>
            <button onClick={nextStep} className="w-full py-2 bg-[var(--slaw-primary-strong)] text-white rounded-lg text-sm font-medium hover:bg-[var(--slaw-primary)] transition-colors">Continue</button>
          </div>
        );

      case "marital_status":
        return (
          <div className="flex flex-wrap gap-2 mt-2">
            {MARITAL_OPTIONS.map(o => (
              <Chip key={o.value} selected={profile.marital_status === o.value} onClick={() => { updateProfile({ marital_status: o.value }); nextStep(); }}>
                {o.label}
              </Chip>
            ))}
          </div>
        );

      case "household":
        return (
          <div className="mt-2 space-y-4 bg-white p-4 rounded-xl border border-[var(--slaw-line)] shadow-sm">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-semibold text-[var(--slaw-ink-soft)] uppercase tracking-wider mb-1">Household Size</label>
                <input type="number" min={1} value={profile.household_size || ""} onChange={e => updateProfile({ household_size: Number(e.target.value) })} className="w-full border border-[var(--slaw-line-strong)] rounded-lg px-3 py-2 text-sm outline-none focus:border-[var(--slaw-primary)]" />
              </div>
              <div>
                <label className="block text-xs font-semibold text-[var(--slaw-ink-soft)] uppercase tracking-wider mb-1">Children</label>
                <input type="number" min={0} value={profile.children_count || ""} onChange={e => updateProfile({ children_count: Number(e.target.value) })} className="w-full border border-[var(--slaw-line-strong)] rounded-lg px-3 py-2 text-sm outline-none focus:border-[var(--slaw-primary)]" />
              </div>
            </div>
            <button onClick={nextStep} className="w-full py-2 bg-[var(--slaw-primary-strong)] text-white rounded-lg text-sm font-medium hover:bg-[var(--slaw-primary)] transition-colors">Continue</button>
          </div>
        );

      case "childcare":
        return (
          <div className="mt-2 space-y-4 bg-white p-4 rounded-xl border border-[var(--slaw-line)] shadow-sm">
            <div>
              <label className="block text-xs font-semibold text-[var(--slaw-ink-soft)] uppercase tracking-wider mb-1">Annual Childcare Cost (CHF)</label>
              <input type="number" value={profile.childcare_cost_chf_yearly || ""} onChange={e => updateProfile({ childcare_cost_chf_yearly: Number(e.target.value) })} className="w-full border border-[var(--slaw-line-strong)] rounded-lg px-3 py-2 text-sm outline-none focus:border-[var(--slaw-primary)]" />
            </div>
            <button onClick={nextStep} className="w-full py-2 bg-[var(--slaw-primary-strong)] text-white rounded-lg text-sm font-medium hover:bg-[var(--slaw-primary)] transition-colors">Continue</button>
          </div>
        );

      case "income":
        return (
          <div className="flex flex-wrap gap-2 mt-2">
            {INCOME_OPTIONS.map(o => (
              <Chip key={o.value} selected={profile.income_band_chf === o.value} onClick={() => { updateProfile({ income_band_chf: o.value }); nextStep(); }}>
                {o.label}
              </Chip>
            ))}
          </div>
        );

      case "pillar3":
        return (
          <div className="mt-2 space-y-4 bg-white p-4 rounded-xl border border-[var(--slaw-line)] shadow-sm">
            <label className="flex items-center gap-2 text-sm font-medium text-[var(--slaw-ink)] cursor-pointer pb-2 border-b border-[var(--slaw-line)]">
              <input type="checkbox" checked={profile.has_third_pillar} onChange={e => updateProfile({ has_third_pillar: e.target.checked })} className="accent-[var(--slaw-primary)] w-4 h-4" />
              I contribute to a 3rd Pillar (3a)
            </label>
            {profile.has_third_pillar && (
              <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }}>
                <label className="block text-xs font-semibold text-[var(--slaw-ink-soft)] uppercase tracking-wider mb-1 mt-2">Contributions this year (CHF)</label>
                <input type="number" value={profile.third_pillar_chf_this_year || ""} onChange={e => updateProfile({ third_pillar_chf_this_year: Number(e.target.value) })} className="w-full border border-[var(--slaw-line-strong)] rounded-lg px-3 py-2 text-sm outline-none focus:border-[var(--slaw-primary)]" />
              </motion.div>
            )}
            <button onClick={nextStep} className="w-full py-2 bg-[var(--slaw-primary-strong)] text-white rounded-lg text-sm font-medium hover:bg-[var(--slaw-primary)] transition-colors">Continue</button>
          </div>
        );

      case "life_events":
        return (
          <div className="mt-2 space-y-4 bg-white p-4 rounded-xl border border-[var(--slaw-line)] shadow-sm">
            <div className="flex flex-wrap gap-2">
              {EVENTS.map(e => {
                const isSelected = profile.recent_life_events.some(ev => ev.event === e.value);
                return (
                  <button
                    key={e.value}
                    onClick={() => {
                      if (isSelected) {
                        updateProfile({ recent_life_events: profile.recent_life_events.filter(ev => ev.event !== e.value) });
                      } else {
                        updateProfile({ recent_life_events: [...profile.recent_life_events, { event: e.value, year: new Date().getFullYear() }] });
                      }
                    }}
                    className={`px-3 py-1.5 rounded-full border text-xs font-medium transition-all ${
                      isSelected 
                        ? "bg-[var(--slaw-primary-soft)] border-[var(--slaw-primary)] text-[var(--slaw-primary-strong)]" 
                        : "bg-white border-[var(--slaw-line-strong)] text-[var(--slaw-ink-soft)] hover:border-[var(--slaw-primary)]"
                    }`}
                  >
                    {e.label}
                  </button>
                );
              })}
            </div>
            <button onClick={nextStep} className="w-full py-2 bg-[var(--slaw-primary-strong)] text-white rounded-lg text-sm font-medium hover:bg-[var(--slaw-primary)] transition-colors">Finish</button>
          </div>
        );

      case "done":
        return (
          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="mt-6 space-y-4">
            <button 
              onClick={() => setIsScanning(true)}
              className="w-full py-4 bg-[var(--slaw-primary-strong)] text-white rounded-xl text-lg font-semibold shadow-md hover:bg-emerald-900 transition-all flex items-center justify-center gap-2"
              disabled={isScanning}
            >
              {isScanning ? (
                <>
                  <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                  Scanning laws...
                </>
              ) : (
                <>
                  Scan my rights <ArrowRight size={20} />
                </>
              )}
            </button>
            <p className="text-center text-xs text-[var(--slaw-ink-soft)]">
              Not a substitute for advice from a Swiss attorney registered with a cantonal bar.
            </p>
          </motion.div>
        );

      default:
        return null;
    }
  };

  const renderCompletedAnswer = (step: StepId) => {
    switch (step) {
      case "canton": return profile.canton;
      case "housing_status": return HOUSING_OPTIONS.find(o => o.value === profile.housing_status)?.label;
      case "housing_details": return `${profile.rent_chf_monthly} CHF/mo (since ${profile.rental_start_year})`;
      case "employment_status": return EMPLOYMENT_OPTIONS.find(o => o.value === profile.employment_status)?.label;
      case "employment_details": return `${profile.weekly_hours}h/week, ${profile.commute_km_daily}km commute`;
      case "marital_status": return MARITAL_OPTIONS.find(o => o.value === profile.marital_status)?.label;
      case "household": return `${profile.household_size} in household, ${profile.children_count} children`;
      case "childcare": return `${profile.childcare_cost_chf_yearly} CHF/yr childcare`;
      case "income": return INCOME_OPTIONS.find(o => o.value === profile.income_band_chf)?.label;
      case "pillar3": return profile.has_third_pillar ? `Pillar 3a: ${profile.third_pillar_chf_this_year} CHF` : "No Pillar 3a";
      case "life_events": return profile.recent_life_events.length > 0 ? profile.recent_life_events.map(e => EVENTS.find(ev => ev.value === e.event)?.label).join(", ") : "No recent events";
      default: return "";
    }
  };

  const getBotQuestion = (step: StepId) => {
    switch (step) {
      case "canton": return "Hello. To check your rights under Swiss law, we first need to know: which canton do you live in?";
      case "housing_status": return "Thanks. What is your current housing situation?";
      case "housing_details": return "Can you share a few details about your rental?";
      case "employment_status": return "Got it. How would you describe your employment status?";
      case "employment_details": return "Could you tell me your weekly hours and daily commute distance?";
      case "marital_status": return "What is your marital status?";
      case "household": return "How many people live in your household, and how many are children?";
      case "childcare": return "What are your approximate annual childcare costs?";
      case "income": return "Which bracket best describes your annual gross household income?";
      case "pillar3": return "Do you contribute to a Pillar 3a account? If so, how much this year?";
      case "life_events": return "Lastly, have you experienced any of these life events recently? (Select all that apply)";
      case "done": return "Thank you. I have everything I need to perform a comprehensive scan of your rights and entitlements.";
      default: return "";
    }
  };

  return (
    <div className="slaw-wizard h-[900px] w-[480px] bg-[#fdfdfd] flex flex-col font-sans overflow-hidden border border-gray-200">
      <header className="px-6 py-5 bg-white border-b border-[var(--slaw-line)] flex items-center justify-between z-10 shadow-sm relative">
        <div>
          <h1 className="text-xl font-semibold text-[var(--slaw-primary-strong)] tracking-tight">Slaw</h1>
          <p className="text-xs text-[var(--slaw-ink-soft)] font-medium">Rights Scan Assistant</p>
        </div>
        <div className="w-10 h-10 rounded-full bg-[var(--slaw-primary-soft)] flex items-center justify-center text-[var(--slaw-primary-strong)]">
          <Briefcase size={20} />
        </div>
      </header>

      <div 
        ref={scrollRef}
        className="flex-1 overflow-y-auto px-5 py-8 space-y-2 scroll-smooth"
        style={{ scrollbarWidth: "none" }}
      >
        {history.map((h, idx) => (
          <div key={h.step + idx}>
            <BotBubble delay={idx === history.length - 1 ? 0.2 : 0}>
              {getBotQuestion(h.step)}
            </BotBubble>

            {h.completed ? (
              <UserBubble onEdit={() => handleEdit(idx)} isEditing={false}>
                {renderCompletedAnswer(h.step)}
              </UserBubble>
            ) : (
              <motion.div
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.3, delay: 0.4 }}
                className="pl-12 flex justify-end w-full mb-8"
              >
                <div className="w-full max-w-[85%]">
                  {renderActiveInput(h.step)}
                </div>
              </motion.div>
            )}
          </div>
        ))}
        {isScanning && (
          <div className="h-12" />
        )}
      </div>
    </div>
  );
}
