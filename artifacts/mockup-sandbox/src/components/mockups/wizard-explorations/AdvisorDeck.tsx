import React, { useState, useEffect } from "react";

const CANTONS = ["AG","AI","AR","BE","BL","BS","FR","GE","GL","GR","JU","LU","NE","NW","OW","SG","SH","SO","SZ","TG","TI","UR","VD","VS","ZG","ZH"];
const EMPLOYMENT_OPTIONS = [
  { value: "employee_full_time", label: "EMP_FT" },
  { value: "employee_part_time", label: "EMP_PT" },
  { value: "self_employed", label: "SELF" },
  { value: "business_owner", label: "OWNER" },
  { value: "unemployed", label: "UNEMP" },
  { value: "student", label: "STUDENT" },
  { value: "retired", label: "RETIRED" },
];
const HOUSING_OPTIONS = [
  { value: "tenant", label: "TENANT" },
  { value: "owner", label: "OWNER" },
  { value: "living_with_family", label: "FAMILY" },
];
const MARITAL_OPTIONS = [
  { value: "single", label: "SNGL" },
  { value: "married", label: "MARR" },
  { value: "registered_partnership", label: "PART" },
  { value: "divorced", label: "DIV" },
  { value: "widowed", label: "WID" },
];
const INCOME_OPTIONS = [
  { value: "lt_30k", label: "< 30K" },
  { value: "30_50k", label: "30-50K" },
  { value: "50_80k", label: "50-80K" },
  { value: "80_120k", label: "80-120K" },
  { value: "120_200k", label: "120-200K" },
  { value: "gt_200k", label: "> 200K" },
];

export default function AdvisorDeck() {
  const [data, setData] = useState({
    canton: "ZH",
    employment_status: "employee_full_time",
    employment_start_year: 2018,
    weekly_hours: 42,
    commute_km_daily: 12,
    housing_status: "tenant",
    rental_start_year: 2018,
    rent_chf_monthly: 2400,
    lease_reference_rate_tracked: true,
    marital_status: "married",
    household_size: 4,
    children_count: 2,
    childcare_cost_chf_yearly: 18000,
    income_band_chf: "120_200k",
    has_third_pillar: true,
    third_pillar_chf_this_year: 7056,
  });

  const [triggers, setTriggers] = useState(0);
  const [estValue, setEstValue] = useState(0);
  const [scanning, setScanning] = useState(false);

  useEffect(() => {
    // Fake live computation
    let tr = 0;
    let val = 0;

    if (data.canton === "ZH") { tr += 2; val += 500; }
    if (data.employment_status.startsWith("employee")) { tr += 3; val += 1200; }
    if (data.commute_km_daily > 10) { tr += 1; val += data.commute_km_daily * 40; }
    if (data.housing_status === "tenant") { tr += 2; val += 800; }
    if (data.children_count > 0) { tr += 4; val += data.children_count * 2500; }
    if (data.has_third_pillar) { tr += 1; val += (data.third_pillar_chf_this_year || 0) * 0.2; }

    setTriggers(tr);
    setEstValue(Math.round(val));
  }, [data]);

  const updateField = (field: string, value: any) => {
    setData(prev => ({ ...prev, [field]: value }));
  };

  const handleScan = () => {
    setScanning(true);
    setTimeout(() => setScanning(false), 1500);
  };

  return (
    <div className="min-h-screen bg-[#0a0a0a] text-[#00ff41] font-mono p-4 flex flex-col h-screen overflow-hidden selection:bg-[#00ff41] selection:text-black">
      <style dangerouslySetInnerHTML={{__html: `
        @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&display=swap');
        .font-mono { font-family: 'JetBrains Mono', monospace; }
        input[type="number"]::-webkit-inner-spin-button,
        input[type="number"]::-webkit-outer-spin-button { -webkit-appearance: none; margin: 0; }
      `}} />
      
      {/* Header */}
      <header className="flex justify-between items-end border-b border-[#00ff41]/30 pb-2 mb-4 shrink-0">
        <div>
          <h1 className="text-xl font-bold tracking-tight">SLAW // ADVISOR TERMINAL v3.4</h1>
          <div className="text-xs text-[#00ff41]/60 mt-1 uppercase">Profile Intake &amp; Live Simulation Engine</div>
        </div>
        <div className="text-right text-xs">
          <div>SYS.STATE: <span className="text-[#00ff41]">ONLINE</span></div>
          <div>DB.SYNC: <span className="text-[#00ff41]">FEDLEX_2024Q3</span></div>
        </div>
      </header>

      {/* Main Layout */}
      <div className="flex gap-6 flex-1 overflow-hidden">
        
        {/* Left: Input Grid */}
        <div className="flex-1 overflow-y-auto pr-2" style={{ scrollbarWidth: 'thin', scrollbarColor: '#00ff41 #0a0a0a' }}>
          <div className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm items-center">
            
            {/* Section: Demographics */}
            <div className="col-span-2 mt-2 mb-1 border-b border-[#00ff41]/20 text-xs text-[#00ff41]/60 uppercase tracking-widest">Demographics &amp; Core</div>
            
            <Label>CANTON</Label>
            <Select value={data.canton} onChange={v => updateField("canton", v)} options={CANTONS.map(c => ({value: c, label: c}))} />

            <Label>MARITAL</Label>
            <Select value={data.marital_status} onChange={v => updateField("marital_status", v)} options={MARITAL_OPTIONS} />

            <Label>HH_SIZE</Label>
            <Input type="number" value={data.household_size} onChange={v => updateField("household_size", parseInt(v)||0)} />

            <Label>CHILDREN</Label>
            <Input type="number" value={data.children_count} onChange={v => updateField("children_count", parseInt(v)||0)} />

            <Label disabled={data.children_count === 0}>CHILDCARE_CHF</Label>
            <Input type="number" disabled={data.children_count === 0} value={data.childcare_cost_chf_yearly} onChange={v => updateField("childcare_cost_chf_yearly", parseInt(v)||0)} />

            {/* Section: Employment */}
            <div className="col-span-2 mt-4 mb-1 border-b border-[#00ff41]/20 text-xs text-[#00ff41]/60 uppercase tracking-widest">Employment &amp; Income</div>

            <Label>EMP_STATUS</Label>
            <Select value={data.employment_status} onChange={v => updateField("employment_status", v)} options={EMPLOYMENT_OPTIONS} />

            <Label>EMP_START_YR</Label>
            <Input type="number" value={data.employment_start_year} onChange={v => updateField("employment_start_year", parseInt(v)||0)} />

            <Label>WK_HOURS</Label>
            <Input type="number" value={data.weekly_hours} onChange={v => updateField("weekly_hours", parseInt(v)||0)} />

            <Label>COMMUTE_KM</Label>
            <Input type="number" value={data.commute_km_daily} onChange={v => updateField("commute_km_daily", parseInt(v)||0)} />

            <Label>INCOME_BAND</Label>
            <Select value={data.income_band_chf} onChange={v => updateField("income_band_chf", v)} options={INCOME_OPTIONS} />

            {/* Section: Housing */}
            <div className="col-span-2 mt-4 mb-1 border-b border-[#00ff41]/20 text-xs text-[#00ff41]/60 uppercase tracking-widest">Housing &amp; Assets</div>

            <Label>HOUSING</Label>
            <Select value={data.housing_status} onChange={v => updateField("housing_status", v)} options={HOUSING_OPTIONS} />

            <Label disabled={data.housing_status !== "tenant"}>RENT_START_YR</Label>
            <Input type="number" disabled={data.housing_status !== "tenant"} value={data.rental_start_year} onChange={v => updateField("rental_start_year", parseInt(v)||0)} />

            <Label disabled={data.housing_status !== "tenant"}>RENT_CHF</Label>
            <Input type="number" disabled={data.housing_status !== "tenant"} value={data.rent_chf_monthly} onChange={v => updateField("rent_chf_monthly", parseInt(v)||0)} />

            <Label disabled={data.housing_status !== "tenant"}>REF_RATE_TRK</Label>
            <Toggle disabled={data.housing_status !== "tenant"} checked={data.lease_reference_rate_tracked} onChange={v => updateField("lease_reference_rate_tracked", v)} />

            <Label>PILLAR_3A</Label>
            <Toggle checked={data.has_third_pillar} onChange={v => updateField("has_third_pillar", v)} />

            <Label disabled={!data.has_third_pillar}>PILLAR_3A_CHF</Label>
            <Input type="number" disabled={!data.has_third_pillar} value={data.third_pillar_chf_this_year} onChange={v => updateField("third_pillar_chf_this_year", parseInt(v)||0)} />

          </div>
        </div>

        {/* Right: Live Telemetry Sidebar */}
        <div className="w-64 shrink-0 flex flex-col border-l border-[#00ff41]/30 pl-6 py-2">
          <div className="text-xs text-[#00ff41]/60 mb-4 uppercase">Live Telemetry</div>
          
          <div className="mb-6">
            <div className="text-xs opacity-70">ACTIVE TRIGGERS</div>
            <div className="text-4xl font-bold tracking-tighter">{triggers.toString().padStart(2, '0')}</div>
          </div>
          
          <div className="mb-8">
            <div className="text-xs opacity-70">EST. DEDUCTION CAP</div>
            <div className="text-2xl font-bold tracking-tighter text-[#00ff41]">
              CHF {estValue.toLocaleString()}
            </div>
          </div>

          <div className="space-y-2 text-[10px] opacity-60 flex-1">
            <div className="flex justify-between border-b border-[#00ff41]/10 pb-1">
              <span>CO/OR Match</span>
              <span>{data.housing_status === 'tenant' ? 'YES' : 'NO'}</span>
            </div>
            <div className="flex justify-between border-b border-[#00ff41]/10 pb-1">
              <span>ZGB Fam</span>
              <span>{data.children_count > 0 ? 'ACTV' : 'IDLE'}</span>
            </div>
            <div className="flex justify-between border-b border-[#00ff41]/10 pb-1">
              <span>DBG Tax</span>
              <span>{data.has_third_pillar ? 'CALC' : 'N/A'}</span>
            </div>
            <div className="flex justify-between border-b border-[#00ff41]/10 pb-1">
              <span>OR 270a</span>
              <span>{data.housing_status === 'tenant' && data.lease_reference_rate_tracked ? 'YES' : 'NO'}</span>
            </div>
          </div>

          <button 
            onClick={handleScan}
            disabled={scanning}
            className="w-full mt-4 bg-[#00ff41] text-black font-bold py-3 uppercase tracking-widest text-sm hover:bg-[#00cc33] focus:outline-none focus:ring-2 focus:ring-[#00ff41] focus:ring-offset-2 focus:ring-offset-[#0a0a0a] disabled:opacity-50 transition-colors"
          >
            {scanning ? "EXECUTING SCAN..." : "RUN FULL SCAN [ENTER]"}
          </button>
        </div>
      </div>
    </div>
  );
}

// Mini UI Components for the dense terminal look

function Label({ children, disabled }: { children: React.ReactNode, disabled?: boolean }) {
  return (
    <div className={`text-right pr-3 py-1 opacity-70 uppercase tracking-wider ${disabled ? 'opacity-30' : ''}`}>
      {children}
    </div>
  );
}

function Input({ value, onChange, type = "text", disabled }: any) {
  return (
    <input 
      type={type}
      value={value}
      onChange={e => onChange(e.target.value)}
      disabled={disabled}
      className={`bg-transparent border border-[#00ff41]/30 text-[#00ff41] px-2 py-1 w-full max-w-[200px] focus:outline-none focus:border-[#00ff41] focus:bg-[#00ff41]/10 disabled:opacity-30 transition-colors ${disabled ? 'cursor-not-allowed' : ''}`}
    />
  );
}

function Select({ value, onChange, options, disabled }: any) {
  return (
    <select
      value={value}
      onChange={e => onChange(e.target.value)}
      disabled={disabled}
      className={`bg-[#0a0a0a] border border-[#00ff41]/30 text-[#00ff41] px-1 py-1 w-full max-w-[200px] focus:outline-none focus:border-[#00ff41] disabled:opacity-30 appearance-none cursor-pointer ${disabled ? 'cursor-not-allowed' : ''}`}
      style={{ backgroundImage: 'linear-gradient(45deg, transparent 50%, #00ff41 50%), linear-gradient(135deg, #00ff41 50%, transparent 50%)', backgroundPosition: 'calc(100% - 10px) calc(1em + 2px), calc(100% - 5px) calc(1em + 2px)', backgroundSize: '5px 5px, 5px 5px', backgroundRepeat: 'no-repeat' }}
    >
      {options.map((o: any) => (
        <option key={o.value} value={o.value}>{o.label}</option>
      ))}
    </select>
  );
}

function Toggle({ checked, onChange, disabled }: any) {
  return (
    <div className="flex items-center h-full">
      <button
        onClick={() => onChange(!checked)}
        disabled={disabled}
        className={`border border-[#00ff41]/50 px-2 py-0.5 text-xs focus:outline-none ${checked ? 'bg-[#00ff41] text-black font-bold' : 'bg-transparent text-[#00ff41]'} disabled:opacity-30 ${disabled ? 'cursor-not-allowed' : ''}`}
      >
        {checked ? 'TRUE' : 'FALSE'}
      </button>
    </div>
  );
}
