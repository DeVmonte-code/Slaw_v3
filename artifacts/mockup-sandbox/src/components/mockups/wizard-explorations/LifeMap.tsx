import React, { useState } from "react";

// --- Google Font Loader ---
const FontLoader = () => (
  <link
    href="https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght@0,9..144,100..900;1,9..144,100..900&family=Nunito:ital,wght@0,200..1000;1,200..1000&display=swap"
    rel="stylesheet"
  />
);

// --- Data & Options ---
const CANTONS = [
  "AG", "AI", "AR", "BE", "BL", "BS", "FR", "GE", "GL", "GR", "JU", "LU",
  "NE", "NW", "OW", "SG", "SH", "SO", "SZ", "TG", "TI", "UR", "VD", "VS", "ZG", "ZH",
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

// --- Types ---
type ProfileData = {
  canton: string;
  housing_status: string;
  rental_start_year: number;
  rent_chf_monthly: number;
  lease_reference_rate_tracked: boolean;
  marital_status: string;
  household_size: number;
  children_count: number;
  childcare_cost_chf_yearly: number;
  employment_status: string;
  employment_start_year: number;
  weekly_hours: number;
  commute_km_daily: number;
  income_band_chf: string;
  has_third_pillar: boolean;
  third_pillar_chf_this_year: number;
};

// --- Zones Definition ---
const ZONES = [
  {
    id: "location",
    title: "Canton",
    image: "/__mockup/images/life-map-switzerland.png",
    fields: ["canton"],
  },
  {
    id: "home",
    title: "Home",
    image: "/__mockup/images/life-map-home.png",
    fields: [
      "housing_status",
      "rental_start_year",
      "rent_chf_monthly",
      "lease_reference_rate_tracked",
    ],
  },
  {
    id: "family",
    title: "Family",
    image: "/__mockup/images/life-map-family.png",
    fields: [
      "marital_status",
      "household_size",
      "children_count",
      "childcare_cost_chf_yearly",
    ],
  },
  {
    id: "work",
    title: "Work & Commute",
    image: "/__mockup/images/life-map-work.png",
    fields: [
      "employment_status",
      "employment_start_year",
      "weekly_hours",
      "commute_km_daily",
    ],
  },
  {
    id: "income",
    title: "Income & Pension",
    image: "/__mockup/images/life-map-income.png",
    fields: [
      "income_band_chf",
      "has_third_pillar",
      "third_pillar_chf_this_year",
    ],
  },
];

// --- Modal Component ---
const Modal = ({
  isOpen,
  onClose,
  title,
  children,
}: {
  isOpen: boolean;
  onClose: () => void;
  title: string;
  children: React.ReactNode;
}) => {
  if (!isOpen) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm transition-all">
      <div
        className="w-full max-w-md scale-100 transform overflow-hidden rounded-2xl bg-[#FFFBF4] p-6 shadow-2xl transition-all border border-[#E8DCC4]"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-center justify-between border-b border-[#E8DCC4] pb-4">
          <h3 className="font-['Fraunces'] text-2xl text-[#2F4F4F]">{title}</h3>
          <button
            onClick={onClose}
            className="rounded-full bg-[#F3EADD] p-2 text-[#2F4F4F] hover:bg-[#E8DCC4] transition-colors"
          >
            <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
        <div className="space-y-4 font-['Nunito'] text-[#4A4A4A]">{children}</div>
      </div>
    </div>
  );
};

// --- Main Component ---
export default function LifeMap() {
  const [data, setData] = useState<ProfileData>({
    canton: "ZH",
    housing_status: "tenant",
    rental_start_year: 2018,
    rent_chf_monthly: 2400,
    lease_reference_rate_tracked: true,
    marital_status: "married",
    household_size: 4,
    children_count: 2,
    childcare_cost_chf_yearly: 18000,
    employment_status: "employee_full_time",
    employment_start_year: 2018,
    weekly_hours: 42,
    commute_km_daily: 12,
    income_band_chf: "120_200k",
    has_third_pillar: true,
    third_pillar_chf_this_year: 7056,
  });

  const [filledZones, setFilledZones] = useState<Record<string, boolean>>({});
  const [activeZone, setActiveZone] = useState<string | null>(null);
  const [isScanning, setIsScanning] = useState(false);

  const handleUpdate = (field: keyof ProfileData, value: any) => {
    setData((prev) => ({ ...prev, [field]: value }));
  };

  const handleCloseModal = () => {
    if (activeZone) {
      setFilledZones((prev) => ({ ...prev, [activeZone]: true }));
    }
    setActiveZone(null);
  };

  const handleRunScan = () => {
    setIsScanning(true);
    setTimeout(() => {
      setIsScanning(false);
      console.log("Scan complete with data:", data);
      alert("Scan complete! (Check console for data)");
    }, 2000);
  };

  const renderFields = (zoneId: string) => {
    switch (zoneId) {
      case "location":
        return (
          <div>
            <label className="block text-sm font-bold mb-1">Your Canton</label>
            <select
              value={data.canton}
              onChange={(e) => handleUpdate("canton", e.target.value)}
              className="w-full rounded-xl border border-[#E8DCC4] bg-white px-4 py-3 focus:border-[#2F4F4F] focus:outline-none"
            >
              {CANTONS.map((c) => (
                <option key={c} value={c}>{c}</option>
              ))}
            </select>
          </div>
        );
      case "home":
        return (
          <>
            <div>
              <label className="block text-sm font-bold mb-1">Housing Status</label>
              <select
                value={data.housing_status}
                onChange={(e) => handleUpdate("housing_status", e.target.value)}
                className="w-full rounded-xl border border-[#E8DCC4] bg-white px-4 py-3 focus:border-[#2F4F4F] focus:outline-none"
              >
                {HOUSING_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>{o.label}</option>
                ))}
              </select>
            </div>
            {data.housing_status === "tenant" && (
              <>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-bold mb-1">Start Year</label>
                    <input
                      type="number"
                      value={data.rental_start_year}
                      onChange={(e) => handleUpdate("rental_start_year", Number(e.target.value))}
                      className="w-full rounded-xl border border-[#E8DCC4] bg-white px-4 py-3 focus:border-[#2F4F4F] focus:outline-none"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-bold mb-1">Rent (CHF)</label>
                    <input
                      type="number"
                      value={data.rent_chf_monthly}
                      onChange={(e) => handleUpdate("rent_chf_monthly", Number(e.target.value))}
                      className="w-full rounded-xl border border-[#E8DCC4] bg-white px-4 py-3 focus:border-[#2F4F4F] focus:outline-none"
                    />
                  </div>
                </div>
                <div className="flex items-center gap-3 pt-2">
                  <input
                    type="checkbox"
                    checked={data.lease_reference_rate_tracked}
                    onChange={(e) => handleUpdate("lease_reference_rate_tracked", e.target.checked)}
                    className="h-5 w-5 rounded border-[#E8DCC4] text-[#2F4F4F] focus:ring-[#2F4F4F]"
                  />
                  <label className="text-sm font-bold">Reference rate tracked in lease</label>
                </div>
              </>
            )}
          </>
        );
      case "family":
        return (
          <>
            <div>
              <label className="block text-sm font-bold mb-1">Marital Status</label>
              <select
                value={data.marital_status}
                onChange={(e) => handleUpdate("marital_status", e.target.value)}
                className="w-full rounded-xl border border-[#E8DCC4] bg-white px-4 py-3 focus:border-[#2F4F4F] focus:outline-none"
              >
                {MARITAL_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>{o.label}</option>
                ))}
              </select>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-bold mb-1">Household Size</label>
                <input
                  type="number"
                  min={1} max={12}
                  value={data.household_size}
                  onChange={(e) => handleUpdate("household_size", Number(e.target.value))}
                  className="w-full rounded-xl border border-[#E8DCC4] bg-white px-4 py-3 focus:border-[#2F4F4F] focus:outline-none"
                />
              </div>
              <div>
                <label className="block text-sm font-bold mb-1">Children</label>
                <input
                  type="number"
                  min={0} max={10}
                  value={data.children_count}
                  onChange={(e) => handleUpdate("children_count", Number(e.target.value))}
                  className="w-full rounded-xl border border-[#E8DCC4] bg-white px-4 py-3 focus:border-[#2F4F4F] focus:outline-none"
                />
              </div>
            </div>
            {data.children_count > 0 && (
              <div>
                <label className="block text-sm font-bold mb-1">Childcare Cost (CHF/year)</label>
                <input
                  type="number"
                  value={data.childcare_cost_chf_yearly}
                  onChange={(e) => handleUpdate("childcare_cost_chf_yearly", Number(e.target.value))}
                  className="w-full rounded-xl border border-[#E8DCC4] bg-white px-4 py-3 focus:border-[#2F4F4F] focus:outline-none"
                />
              </div>
            )}
          </>
        );
      case "work":
        return (
          <>
            <div>
              <label className="block text-sm font-bold mb-1">Employment Status</label>
              <select
                value={data.employment_status}
                onChange={(e) => handleUpdate("employment_status", e.target.value)}
                className="w-full rounded-xl border border-[#E8DCC4] bg-white px-4 py-3 focus:border-[#2F4F4F] focus:outline-none"
              >
                {EMPLOYMENT_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>{o.label}</option>
                ))}
              </select>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-bold mb-1">Start Year</label>
                <input
                  type="number"
                  value={data.employment_start_year}
                  onChange={(e) => handleUpdate("employment_start_year", Number(e.target.value))}
                  className="w-full rounded-xl border border-[#E8DCC4] bg-white px-4 py-3 focus:border-[#2F4F4F] focus:outline-none"
                />
              </div>
              <div>
                <label className="block text-sm font-bold mb-1">Weekly Hours</label>
                <input
                  type="number"
                  value={data.weekly_hours}
                  onChange={(e) => handleUpdate("weekly_hours", Number(e.target.value))}
                  className="w-full rounded-xl border border-[#E8DCC4] bg-white px-4 py-3 focus:border-[#2F4F4F] focus:outline-none"
                />
              </div>
            </div>
            <div>
              <label className="block text-sm font-bold mb-1">Commute (km/day)</label>
              <input
                type="number"
                value={data.commute_km_daily}
                onChange={(e) => handleUpdate("commute_km_daily", Number(e.target.value))}
                className="w-full rounded-xl border border-[#E8DCC4] bg-white px-4 py-3 focus:border-[#2F4F4F] focus:outline-none"
              />
            </div>
          </>
        );
      case "income":
        return (
          <>
            <div>
              <label className="block text-sm font-bold mb-1">Income Band (CHF/year)</label>
              <select
                value={data.income_band_chf}
                onChange={(e) => handleUpdate("income_band_chf", e.target.value)}
                className="w-full rounded-xl border border-[#E8DCC4] bg-white px-4 py-3 focus:border-[#2F4F4F] focus:outline-none"
              >
                {INCOME_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>{o.label}</option>
                ))}
              </select>
            </div>
            <div className="flex items-center gap-3 pt-2">
              <input
                type="checkbox"
                checked={data.has_third_pillar}
                onChange={(e) => handleUpdate("has_third_pillar", e.target.checked)}
                className="h-5 w-5 rounded border-[#E8DCC4] text-[#2F4F4F] focus:ring-[#2F4F4F]"
              />
              <label className="text-sm font-bold">Has 3rd Pillar (Pillar 3a)</label>
            </div>
            {data.has_third_pillar && (
              <div>
                <label className="block text-sm font-bold mb-1">3rd Pillar Contributions This Year (CHF)</label>
                <input
                  type="number"
                  value={data.third_pillar_chf_this_year}
                  onChange={(e) => handleUpdate("third_pillar_chf_this_year", Number(e.target.value))}
                  className="w-full rounded-xl border border-[#E8DCC4] bg-white px-4 py-3 focus:border-[#2F4F4F] focus:outline-none"
                />
              </div>
            )}
          </>
        );
      default:
        return null;
    }
  };

  const allFilled = ZONES.every((z) => filledZones[z.id]);

  return (
    <div className="min-h-screen bg-[#FFFDF9] font-['Nunito'] text-[#4A4A4A] overflow-x-hidden relative">
      <FontLoader />
      
      {/* Decorative Background Elements */}
      <div className="absolute top-0 left-0 w-full h-64 bg-gradient-to-b from-[#E8F0EA] to-transparent pointer-events-none" />
      <div className="absolute -top-20 -right-20 w-64 h-64 rounded-full bg-[#FDE8B5] opacity-50 blur-3xl pointer-events-none" />
      <div className="absolute top-40 -left-20 w-48 h-48 rounded-full bg-[#E1EED3] opacity-60 blur-3xl pointer-events-none" />
      
      <main className="relative mx-auto max-w-4xl p-6 pt-12 md:p-12">
        <header className="mb-12 text-center">
          <h1 className="font-['Fraunces'] text-5xl font-bold text-[#2F4F4F] mb-4">
            Map of Your Life
          </h1>
          <p className="mx-auto max-w-xl text-lg text-[#6A7C7C]">
            Welcome! Tap on each place in your village to tell us a bit about your life in Switzerland. We'll find all the rights and protections you're entitled to.
          </p>
        </header>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 mb-16">
          {ZONES.map((zone, idx) => {
            const isFilled = filledZones[zone.id];
            return (
              <button
                key={zone.id}
                onClick={() => setActiveZone(zone.id)}
                className={`group relative flex flex-col items-center rounded-3xl p-6 transition-all duration-300 
                  ${
                    isFilled
                      ? "bg-white shadow-[0_8px_30px_rgb(0,0,0,0.06)] border-2 border-[#D1E2C9]"
                      : "bg-[#F9F4EB] border-2 border-dashed border-[#E8DCC4] hover:bg-white hover:shadow-md hover:-translate-y-1"
                  }
                  ${idx === 0 ? "md:col-span-2 lg:col-span-3 lg:w-1/2 lg:mx-auto" : ""}
                `}
              >
                <div
                  className={`relative mb-4 h-32 w-32 overflow-hidden rounded-full transition-all duration-500 ${
                    isFilled ? "scale-105 shadow-inner" : "grayscale opacity-80 group-hover:grayscale-0 group-hover:opacity-100"
                  }`}
                >
                  <img
                    src={zone.image}
                    alt={zone.title}
                    className="h-full w-full object-cover object-center"
                  />
                  {isFilled && (
                    <div className="absolute inset-0 rounded-full border-4 border-[#8EBE77] shadow-[inset_0_0_15px_rgba(142,190,119,0.5)]" />
                  )}
                </div>
                
                <h2 className="font-['Fraunces'] text-2xl font-semibold text-[#2F4F4F]">
                  {zone.title}
                </h2>
                
                <div className="mt-3 flex items-center justify-center">
                  {isFilled ? (
                    <span className="flex items-center gap-1 text-sm font-bold text-[#8EBE77] bg-[#F0F7EC] px-3 py-1 rounded-full">
                      <svg className="h-4 w-4" fill="currentColor" viewBox="0 0 20 20">
                        <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                      </svg>
                      Completed
                    </span>
                  ) : (
                    <span className="text-sm font-bold text-[#A5957C]">
                      Tap to fill
                    </span>
                  )}
                </div>
              </button>
            );
          })}
        </div>

        <div className="text-center pb-20">
          <div className={`transition-all duration-700 ${allFilled ? 'opacity-100 translate-y-0' : 'opacity-40 translate-y-4 pointer-events-none'}`}>
            <button
              onClick={handleRunScan}
              disabled={isScanning || !allFilled}
              className={`relative overflow-hidden rounded-full bg-[#D46B4E] px-10 py-5 font-['Fraunces'] text-2xl font-bold text-white transition-all hover:bg-[#C25B3E] hover:shadow-[0_8px_30px_rgba(212,107,78,0.4)] hover:-translate-y-1 disabled:opacity-50`}
            >
              {isScanning ? (
                <span className="flex items-center justify-center gap-3">
                  <svg className="h-6 w-6 animate-spin" viewBox="0 0 24 24" fill="none">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                  </svg>
                  Exploring your rights...
                </span>
              ) : (
                "Run Rights Scan"
              )}
            </button>
            <p className="mt-6 text-sm text-[#8E9B9B] max-w-md mx-auto">
              Not a substitute for advice from a Swiss attorney registered with a cantonal bar. We keep your data safe and cozy.
            </p>
          </div>
        </div>
      </main>

      <Modal
        isOpen={activeZone !== null}
        onClose={handleCloseModal}
        title={activeZone ? ZONES.find((z) => z.id === activeZone)?.title || "" : ""}
      >
        {activeZone && renderFields(activeZone)}
        <div className="mt-8">
          <button
            onClick={handleCloseModal}
            className="w-full rounded-xl bg-[#2F4F4F] px-4 py-3 font-bold text-white transition-colors hover:bg-[#1E3333]"
          >
            Save &amp; Return to Map
          </button>
        </div>
      </Modal>
    </div>
  );
}
