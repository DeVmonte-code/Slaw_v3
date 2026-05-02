import React, { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Briefcase,
  Building,
  Baby,
  Heart,
  PiggyBank,
  GraduationCap,
  MapPin,
  TrendingUp,
  Home,
  Users,
  Search,
  CheckCircle2,
  Calendar,
  Clock,
  Car,
  FileText,
  DollarSign
} from "lucide-react";
import "./_group.css";
import type { ContextProfile, LifeEvent, LifeEventKind } from "./types";
import { DEFAULT_CONTEXT_PROFILE } from "./types";

const CANTONS = [
  "AG", "AI", "AR", "BE", "BL", "BS", "FR", "GE", "GL", "GR", "JU", "LU",
  "NE", "NW", "OW", "SG", "SH", "SO", "SZ", "TG", "TI", "UR", "VD", "VS", "ZG", "ZH",
];

const INCOME_OPTIONS = [
  { value: "lt_30k", label: "Under CHF 30k" },
  { value: "30_50k", label: "CHF 30k – 50k" },
  { value: "50_80k", label: "CHF 50k – 80k" },
  { value: "80_120k", label: "CHF 80k – 120k" },
  { value: "120_200k", label: "CHF 120k – 200k" },
  { value: "gt_200k", label: "Over CHF 200k" },
];

export default function LifeSnapshotTiles() {
  const [profile, setProfile] = useState<ContextProfile>(DEFAULT_CONTEXT_PROFILE);

  const [isScanning, setIsScanning] = useState(false);

  const updateProfile = <K extends keyof ContextProfile>(
    key: K,
    value: ContextProfile[K],
  ) => {
    setProfile((prev) => ({ ...prev, [key]: value }));
  };

  const handleLifeEventToggle = (eventKind: LifeEventKind) => {
    setProfile((prev) => {
      const exists = prev.recent_life_events.some((e) => e.event === eventKind);
      const next: LifeEvent[] = exists
        ? prev.recent_life_events.filter((e) => e.event !== eventKind)
        : [
            ...prev.recent_life_events,
            { event: eventKind, year: new Date().getFullYear() },
          ];
      return { ...prev, recent_life_events: next };
    });
  };

  const calculateRightsCount = () => {
    let count = 12; // Base rights
    if (profile.housing_status === 'tenant') count += 5;
    if (profile.children_count > 0) count += 8;
    if (profile.has_third_pillar) count += 3;
    if (profile.marital_status === 'married') count += 4;
    count += profile.recent_life_events.length * 2;
    return count;
  };

  return (
    <div className="slaw-wizard min-h-screen bg-gray-50/50 pb-20 font-sans selection:bg-emerald-100 selection:text-emerald-900">
      <header className="sticky top-0 z-10 bg-white/80 backdrop-blur-md border-b border-gray-200/50 px-6 py-4 shadow-sm">
        <div className="max-w-md mx-auto flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg bg-emerald-700 flex items-center justify-center shadow-sm">
              <Search className="w-4 h-4 text-white" />
            </div>
            <span className="font-semibold text-gray-900">Slaw Profile</span>
          </div>
          <div className="flex items-center gap-2 text-sm font-medium text-gray-600 bg-gray-100/80 px-3 py-1.5 rounded-full">
            <MapPin className="w-4 h-4 text-emerald-600" />
            <select 
              value={profile.canton}
              onChange={(e) => updateProfile("canton", e.target.value)}
              className="bg-transparent border-none outline-none cursor-pointer focus:ring-0 p-0 text-gray-800"
            >
              {CANTONS.map(c => <option key={c} value={c}>{c}</option>)}
            </select>
          </div>
        </div>
      </header>

      <main className="max-w-md mx-auto p-6 space-y-8">
        <div className="space-y-2">
          <h1 className="text-2xl font-bold text-gray-900 tracking-tight">Your life snapshot</h1>
          <p className="text-gray-500 text-sm leading-relaxed">
            Select the tiles that describe your current situation. We'll only ask for the details we need to find your legal rights.
          </p>
        </div>

        <div className="space-y-6">
          {/* Housing Section */}
          <Section title="Housing">
            <div className="grid grid-cols-2 gap-3">
              <Tile 
                selected={profile.housing_status === "tenant"} 
                onClick={() => updateProfile("housing_status", "tenant")}
                icon={<Building />}
                label="Tenant"
              />
              <Tile 
                selected={profile.housing_status === "owner"} 
                onClick={() => updateProfile("housing_status", "owner")}
                icon={<Home />}
                label="Owner"
              />
            </div>
            <AnimatePresence>
              {profile.housing_status === "tenant" && (
                <motion.div 
                  initial={{ opacity: 0, height: 0, marginTop: 0 }}
                  animate={{ opacity: 1, height: "auto", marginTop: 12 }}
                  exit={{ opacity: 0, height: 0, marginTop: 0 }}
                  className="overflow-hidden"
                >
                  <div className="bg-white rounded-xl p-4 border border-emerald-100 shadow-sm space-y-4">
                    <Field label="Monthly Rent (CHF)" icon={<DollarSign className="w-4 h-4 text-emerald-600"/>}>
                      <input 
                        type="number" 
                        value={profile.rent_chf_monthly} 
                        onChange={(e) => updateProfile("rent_chf_monthly", Number(e.target.value))}
                        className="w-full text-right outline-none text-gray-900 font-medium"
                      />
                    </Field>
                    <Field label="Move-in Year" icon={<Calendar className="w-4 h-4 text-emerald-600"/>}>
                      <input 
                        type="number" 
                        value={profile.rental_start_year} 
                        onChange={(e) => updateProfile("rental_start_year", Number(e.target.value))}
                        className="w-full text-right outline-none text-gray-900 font-medium"
                      />
                    </Field>
                    <label className="flex items-center gap-3 pt-2 cursor-pointer group">
                      <div className={`w-5 h-5 rounded flex items-center justify-center border transition-colors ${profile.lease_reference_rate_tracked ? 'bg-emerald-600 border-emerald-600' : 'border-gray-300 group-hover:border-emerald-400'}`}>
                        {profile.lease_reference_rate_tracked && <CheckCircle2 className="w-3.5 h-3.5 text-white" />}
                      </div>
                      <input 
                        type="checkbox" 
                        className="hidden"
                        checked={profile.lease_reference_rate_tracked}
                        onChange={(e) => updateProfile("lease_reference_rate_tracked", e.target.checked)}
                      />
                      <span className="text-sm font-medium text-gray-700 group-hover:text-gray-900 transition-colors">Lease tracks reference rate</span>
                    </label>
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </Section>

          {/* Work & Income */}
          <Section title="Work & Income">
            <div className="grid grid-cols-2 gap-3 mb-3">
              <Tile 
                selected={profile.employment_status.includes("employee")} 
                onClick={() => updateProfile("employment_status", "employee_full_time")}
                icon={<Briefcase />}
                label="Employee"
              />
              <Tile 
                selected={profile.employment_status === "self_employed"} 
                onClick={() => updateProfile("employment_status", "self_employed")}
                icon={<TrendingUp />}
                label="Self-Employed"
              />
            </div>
            
            <AnimatePresence>
              {profile.employment_status.includes("employee") && (
                <motion.div 
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: "auto", marginBottom: 12 }}
                  exit={{ opacity: 0, height: 0, marginBottom: 0 }}
                  className="overflow-hidden"
                >
                  <div className="bg-white rounded-xl p-4 border border-emerald-100 shadow-sm space-y-4">
                    <Field label="Weekly Hours" icon={<Clock className="w-4 h-4 text-emerald-600"/>}>
                      <input 
                        type="number" 
                        value={profile.weekly_hours} 
                        onChange={(e) => updateProfile("weekly_hours", Number(e.target.value))}
                        className="w-full text-right outline-none text-gray-900 font-medium"
                      />
                    </Field>
                    <Field label="Daily Commute (km)" icon={<Car className="w-4 h-4 text-emerald-600"/>}>
                      <input 
                        type="number" 
                        value={profile.commute_km_daily} 
                        onChange={(e) => updateProfile("commute_km_daily", Number(e.target.value))}
                        className="w-full text-right outline-none text-gray-900 font-medium"
                      />
                    </Field>
                  </div>
                </motion.div>
              )}
            </AnimatePresence>

            <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden mt-3">
              <div className="px-4 py-3 flex items-center justify-between border-b border-gray-100">
                <span className="text-sm font-medium text-gray-700 flex items-center gap-2">
                  <FileText className="w-4 h-4 text-gray-400" />
                  Household Income
                </span>
                <select 
                  value={profile.income_band_chf}
                  onChange={(e) => updateProfile("income_band_chf", e.target.value)}
                  className="text-sm font-medium text-emerald-700 bg-emerald-50 py-1 px-2 rounded outline-none cursor-pointer"
                >
                  {INCOME_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
                </select>
              </div>
            </div>
          </Section>

          {/* Family & Status */}
          <Section title="Family & Status">
            <div className="grid grid-cols-2 gap-3">
              <Tile 
                selected={profile.marital_status === "married"} 
                onClick={() => updateProfile("marital_status", profile.marital_status === "married" ? "single" : "married")}
                icon={<Heart />}
                label={profile.marital_status === "married" ? "Married" : "Not Married"}
                activeLabel="Married"
              />
              <Tile 
                selected={profile.children_count > 0} 
                onClick={() => updateProfile("children_count", profile.children_count > 0 ? 0 : 2)}
                icon={<Baby />}
                label="Have Children"
              />
            </div>
            
            <AnimatePresence>
              {profile.children_count > 0 && (
                <motion.div 
                  initial={{ opacity: 0, height: 0, marginTop: 0 }}
                  animate={{ opacity: 1, height: "auto", marginTop: 12 }}
                  exit={{ opacity: 0, height: 0, marginTop: 0 }}
                  className="overflow-hidden"
                >
                  <div className="bg-white rounded-xl p-4 border border-emerald-100 shadow-sm space-y-4">
                    <Field label="Number of Children" icon={<Users className="w-4 h-4 text-emerald-600"/>}>
                      <input 
                        type="number" 
                        min="1"
                        value={profile.children_count} 
                        onChange={(e) => updateProfile("children_count", Number(e.target.value))}
                        className="w-full text-right outline-none text-gray-900 font-medium"
                      />
                    </Field>
                    <Field label="Childcare (CHF/yr)" icon={<DollarSign className="w-4 h-4 text-emerald-600"/>}>
                      <input 
                        type="number" 
                        value={profile.childcare_cost_chf_yearly} 
                        onChange={(e) => updateProfile("childcare_cost_chf_yearly", Number(e.target.value))}
                        className="w-full text-right outline-none text-gray-900 font-medium"
                      />
                    </Field>
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </Section>

          {/* Wealth & Savings */}
          <Section title="Wealth & Savings">
             <Tile 
                selected={profile.has_third_pillar} 
                onClick={() => updateProfile("has_third_pillar", !profile.has_third_pillar)}
                icon={<PiggyBank />}
                label="Contribute to Pillar 3a"
                fullWidth
              />
              <AnimatePresence>
              {profile.has_third_pillar && (
                <motion.div 
                  initial={{ opacity: 0, height: 0, marginTop: 0 }}
                  animate={{ opacity: 1, height: "auto", marginTop: 12 }}
                  exit={{ opacity: 0, height: 0, marginTop: 0 }}
                  className="overflow-hidden"
                >
                  <div className="bg-white rounded-xl p-4 border border-emerald-100 shadow-sm">
                    <Field label="This Year's Contribution" icon={<DollarSign className="w-4 h-4 text-emerald-600"/>}>
                      <input 
                        type="number" 
                        value={profile.third_pillar_chf_this_year} 
                        onChange={(e) => updateProfile("third_pillar_chf_this_year", Number(e.target.value))}
                        className="w-full text-right outline-none text-gray-900 font-medium"
                      />
                    </Field>
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </Section>

          {/* Recent Life Events */}
          <Section title="Recent Life Events">
             <div className="grid grid-cols-2 gap-3">
              {([
                { id: "moved_canton",      label: "Moved Canton",      icon: <MapPin /> },
                { id: "had_child",         label: "Had a Child",       icon: <Baby /> },
                { id: "got_married",       label: "Got Married",       icon: <Heart /> },
                { id: "got_divorced",      label: "Got Divorced",      icon: <Heart /> },
                { id: "lost_job",          label: "Lost a Job",        icon: <Briefcase /> },
                { id: "started_business",  label: "Started Business",  icon: <Briefcase /> },
                { id: "started_studies",   label: "Started Studies",   icon: <GraduationCap /> },
                { id: "bought_property",   label: "Bought Property",   icon: <Home /> },
                { id: "retired",           label: "Retired",           icon: <Clock /> },
              ] as { id: LifeEventKind; label: string; icon: React.ReactNode }[]).map(event => (
                <Tile
                  key={event.id}
                  selected={profile.recent_life_events.some((e) => e.event === event.id)}
                  onClick={() => handleLifeEventToggle(event.id)}
                  icon={event.icon}
                  label={event.label}
                  small
                />
              ))}
            </div>
          </Section>

        </div>
      </main>

      {/* Sticky Bottom Action */}
      <div className="fixed bottom-0 left-0 right-0 p-6 bg-gradient-to-t from-gray-50 via-gray-50 to-transparent pt-12">
        <div className="max-w-md mx-auto">
          <button 
            onClick={() => {
              setIsScanning(true);
              setTimeout(() => setIsScanning(false), 2000);
            }}
            className={`w-full relative overflow-hidden flex items-center justify-center gap-3 bg-emerald-700 hover:bg-emerald-800 text-white p-4 rounded-2xl font-semibold shadow-lg shadow-emerald-900/20 transition-all active:scale-[0.98] ${isScanning ? 'opacity-90' : ''}`}
          >
            {isScanning ? (
              <motion.div 
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                className="flex items-center gap-2"
              >
                <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                <span>Scanning {calculateRightsCount()} potential rights...</span>
              </motion.div>
            ) : (
              <>
                <Search className="w-5 h-5" />
                <span>Run Rights Scan</span>
                <span className="absolute right-4 bg-emerald-800/50 px-2 py-0.5 rounded-full text-xs font-medium text-emerald-100 flex items-center gap-1">
                  <TrendingUp className="w-3 h-3" />
                  ~{calculateRightsCount()} rights
                </span>
              </>
            )}
          </button>
          <p className="text-center text-[10px] text-gray-400 mt-4 px-4 leading-relaxed">
            Not a substitute for advice from a Swiss attorney registered with a cantonal bar.
          </p>
        </div>
      </div>
    </div>
  );
}

function Section({ title, children }: { title: string, children: React.ReactNode }) {
  return (
    <section>
      <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-3 px-1">{title}</h2>
      {children}
    </section>
  );
}

function Tile({ 
  selected, 
  onClick, 
  icon, 
  label,
  activeLabel,
  fullWidth = false,
  small = false
}: { 
  selected: boolean; 
  onClick: () => void; 
  icon: React.ReactNode; 
  label: string; 
  activeLabel?: string;
  fullWidth?: boolean;
  small?: boolean;
}) {
  return (
    <button
      onClick={onClick}
      className={`
        relative flex flex-col text-left transition-all duration-200 outline-none
        ${fullWidth ? 'w-full' : 'w-full'}
        ${small ? 'p-3 rounded-xl' : 'p-4 rounded-2xl'}
        ${selected 
          ? 'bg-emerald-50 border-2 border-emerald-500 shadow-md shadow-emerald-100' 
          : 'bg-white border-2 border-gray-100 hover:border-gray-200 shadow-sm hover:shadow'}
      `}
      style={{
        transform: selected ? 'translateY(-1px)' : 'none'
      }}
    >
      <div className={`
        flex items-center justify-center rounded-xl mb-3 transition-colors
        ${small ? 'w-8 h-8' : 'w-10 h-10'}
        ${selected ? 'bg-emerald-100 text-emerald-700' : 'bg-gray-50 text-gray-400'}
      `}>
        {React.cloneElement(icon as React.ReactElement, { 
          className: small ? 'w-4 h-4' : 'w-5 h-5' 
        })}
      </div>
      <span className={`font-semibold leading-tight transition-colors ${selected ? 'text-emerald-900' : 'text-gray-600'} ${small ? 'text-sm' : ''}`}>
        {selected ? (activeLabel || label) : label}
      </span>
      {selected && (
        <motion.div 
          layoutId="active-indicator"
          className="absolute top-3 right-3 w-2 h-2 rounded-full bg-emerald-500"
          initial={{ scale: 0 }}
          animate={{ scale: 1 }}
        />
      )}
    </button>
  );
}

function Field({ label, icon, children }: { label: string, icon: React.ReactNode, children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-4 p-1">
      <div className="flex items-center gap-2 text-sm text-gray-600 whitespace-nowrap">
        {icon}
        {label}
      </div>
      <div className="w-24 border-b border-gray-200 focus-within:border-emerald-500 transition-colors pb-1">
        {children}
      </div>
    </div>
  );
}
