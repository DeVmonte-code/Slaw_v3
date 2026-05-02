import React, { useState, useRef, useEffect } from "react";
import { UploadCloud, FileText, CheckCircle2, ChevronRight, AlertCircle, RefreshCw, Briefcase, Home, Users, Wallet } from "lucide-react";
import "./_group.css";

const CANTONS = ["AG","AI","AR","BE","BL","BS","FR","GE","GL","GR","JU","LU","NE","NW","OW","SG","SH","SO","SZ","TG","TI","UR","VD","VS","ZG","ZH"];

export default function UploadFirst() {
  const [step, setStep] = useState<"upload" | "processing" | "review">("upload");
  const [progress, setProgress] = useState(0);
  const [files, setFiles] = useState<{name: string, type: string}[]>([]);
  
  // Data state combining extracted and manual fields
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
    third_pillar_chf_this_year: 7056
  });

  const [missingFields, setMissingFields] = useState(["canton", "commute_km_daily"]);
  const [scanning, setScanning] = useState(false);

  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      handleFiles(Array.from(e.dataTransfer.files));
    }
  };

  const handleFiles = (selectedFiles: File[]) => {
    setFiles(selectedFiles.map(f => ({ name: f.name, type: f.type })));
    setStep("processing");
  };

  useEffect(() => {
    if (step === "processing") {
      const interval = setInterval(() => {
        setProgress(p => {
          if (p >= 100) {
            clearInterval(interval);
            setTimeout(() => setStep("review"), 500);
            return 100;
          }
          return p + 2;
        });
      }, 30);
      return () => clearInterval(interval);
    }
  }, [step]);

  const updateData = (key: string, value: any) => {
    setData(prev => ({ ...prev, [key]: value }));
    if (missingFields.includes(key)) {
      setMissingFields(prev => prev.filter(f => f !== key));
    }
  };

  const runScan = () => {
    setScanning(true);
    setTimeout(() => {
      setScanning(false);
      console.log("Running scan with data:", data);
    }, 1500);
  };

  return (
    <div className="upload-first-theme min-h-screen bg-[var(--color-bank-bg)] text-[var(--color-bank-text)] font-sans selection:bg-[var(--color-brand-soft)]">
      {/* Header */}
      <header className="border-b border-[var(--color-bank-border)] bg-[var(--color-bank-surface)] px-8 py-6 sticky top-0 z-10">
        <div className="max-w-4xl mx-auto flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-serif text-[var(--color-brand)] font-semibold tracking-tight">
              Swiss Legal Rights Scan
            </h1>
            <p className="text-sm text-[var(--color-bank-text-muted)] mt-1">
              Secure, automated entitlement discovery
            </p>
          </div>
          <div className="flex items-center space-x-2 text-xs font-medium text-[var(--color-bank-text-muted)] bg-[var(--color-bank-bg)] px-3 py-1.5 rounded-full border border-[var(--color-bank-border)]">
            <CheckCircle2 className="w-3.5 h-3.5 text-[var(--color-brand)]" />
            <span>End-to-End Encrypted</span>
          </div>
        </div>
      </header>

      <main className="max-w-4xl mx-auto p-8 py-12">
        {step === "upload" && (
          <div className="animate-slide-up max-w-2xl mx-auto">
            <div className="text-center mb-10">
              <h2 className="text-3xl font-serif text-[var(--color-bank-text)] mb-4">
                Let your documents do the work
              </h2>
              <p className="text-[var(--color-bank-text-muted)] text-lg leading-relaxed">
                Provide your latest Salary Statement (Lohnausweis) and Rental Agreement. 
                Our secure extraction engine will pre-fill your profile instantly, 
                leaving you with only a few confirmations.
              </p>
            </div>

            <div 
              onDragOver={(e) => e.preventDefault()}
              onDrop={handleDrop}
              onClick={() => fileInputRef.current?.click()}
              className="border-2 border-dashed border-[var(--color-bank-border)] rounded-xl bg-[var(--color-bank-surface)] p-12 text-center cursor-pointer hover:border-[var(--color-brand)] hover:bg-[var(--color-brand-soft)] transition-colors duration-300 group"
            >
              <input 
                type="file" 
                multiple 
                className="hidden" 
                ref={fileInputRef}
                onChange={(e) => e.target.files && handleFiles(Array.from(e.target.files))}
              />
              <div className="w-16 h-16 rounded-full bg-[var(--color-bank-bg)] flex items-center justify-center mx-auto mb-6 group-hover:scale-110 transition-transform duration-300 group-hover:bg-white shadow-sm border border-[var(--color-bank-border)]">
                <UploadCloud className="w-8 h-8 text-[var(--color-brand)]" />
              </div>
              <h3 className="text-lg font-medium text-[var(--color-bank-text)] mb-2">
                Drop your documents here
              </h3>
              <p className="text-sm text-[var(--color-bank-text-muted)] mb-6">
                PDF, JPG, or PNG. Maximum 50MB per file.
              </p>
              <div className="inline-flex items-center justify-center px-6 py-2.5 rounded-lg bg-[var(--color-brand)] text-white text-sm font-medium hover:bg-[var(--color-brand-hover)] transition-colors">
                Browse Files
              </div>
            </div>

            <div className="mt-8 flex justify-center space-x-6 text-sm text-[var(--color-bank-text-muted)]">
              <div className="flex items-center"><CheckCircle2 className="w-4 h-4 mr-2 text-[var(--color-brand-muted)]" /> No data stored permanently</div>
              <div className="flex items-center"><CheckCircle2 className="w-4 h-4 mr-2 text-[var(--color-brand-muted)]" /> Bank-grade encryption</div>
            </div>
          </div>
        )}

        {step === "processing" && (
          <div className="animate-slide-up max-w-md mx-auto text-center py-20">
            <div className="w-20 h-20 relative mx-auto mb-8">
              <svg className="animate-spin w-full h-full text-[var(--color-brand-soft)]" viewBox="0 0 100 100">
                <circle className="opacity-25" cx="50" cy="50" r="45" stroke="currentColor" strokeWidth="4" fill="none" />
                <path className="opacity-75 text-[var(--color-brand)]" fill="currentColor" d="M50 5a45 45 0 0 1 45 45h-4A41 41 0 0 0 50 9V5z" />
              </svg>
              <div className="absolute inset-0 flex items-center justify-center text-sm font-medium text-[var(--color-brand)]">
                {progress}%
              </div>
            </div>
            <h2 className="text-2xl font-serif text-[var(--color-bank-text)] mb-3">
              Extracting profile data
            </h2>
            <p className="text-[var(--color-bank-text-muted)]">
              Analyzing {files.length} document{files.length !== 1 ? 's' : ''}...
            </p>
            <div className="mt-8 space-y-3 text-sm text-left w-64 mx-auto">
              <div className="flex items-center text-[var(--color-bank-text-muted)]">
                {progress > 20 ? <CheckCircle2 className="w-4 h-4 mr-3 text-[var(--color-brand)]" /> : <div className="w-4 h-4 mr-3 border border-[var(--color-bank-border)] rounded-full" />}
                Parsing Lohnausweis structure
              </div>
              <div className="flex items-center text-[var(--color-bank-text-muted)]">
                {progress > 60 ? <CheckCircle2 className="w-4 h-4 mr-3 text-[var(--color-brand)]" /> : <div className="w-4 h-4 mr-3 border border-[var(--color-bank-border)] rounded-full" />}
                Identifying tenancy parameters
              </div>
              <div className="flex items-center text-[var(--color-bank-text-muted)]">
                {progress > 90 ? <CheckCircle2 className="w-4 h-4 mr-3 text-[var(--color-brand)]" /> : <div className="w-4 h-4 mr-3 border border-[var(--color-bank-border)] rounded-full" />}
                Cross-referencing legal domains
              </div>
            </div>
          </div>
        )}

        {step === "review" && (
          <div className="animate-slide-up grid grid-cols-12 gap-10">
            {/* Left Column: Data Review */}
            <div className="col-span-8 space-y-8">
              <div>
                <h2 className="text-3xl font-serif text-[var(--color-bank-text)] mb-2">
                  Profile Extracted
                </h2>
                <p className="text-[var(--color-bank-text-muted)]">
                  We've populated your profile from the provided documents. Please confirm the details below and fill in any missing information to proceed.
                </p>
              </div>

              {/* Extraction Confidence Banner */}
              <div className="bg-[var(--color-brand-soft)] border border-[var(--color-brand-muted)] rounded-xl p-4 flex items-start space-x-4">
                <div className="p-2 bg-white rounded-full text-[var(--color-brand)] shadow-sm">
                  <CheckCircle2 className="w-5 h-5" />
                </div>
                <div>
                  <h4 className="text-sm font-semibold text-[var(--color-brand-hover)]">High Confidence Match</h4>
                  <p className="text-sm text-[var(--color-brand-hover)] mt-1 opacity-80">15 of 17 required fields were successfully extracted from your documents.</p>
                </div>
              </div>

              {/* Data Sections */}
              <div className="space-y-6">
                
                {/* Employment Section */}
                <div className="bg-[var(--color-bank-surface)] border border-[var(--color-bank-border)] rounded-xl overflow-hidden shadow-sm">
                  <div className="px-6 py-4 border-b border-[var(--color-bank-border)] bg-[var(--color-bank-bg)] flex items-center">
                    <Briefcase className="w-4 h-4 mr-3 text-[var(--color-bank-text-muted)]" />
                    <h3 className="font-medium">Employment &amp; Income</h3>
                  </div>
                  <div className="p-6 grid grid-cols-2 gap-x-8 gap-y-6">
                    <Field label="Status" value={data.employment_status} />
                    <Field label="Income Band" value={data.income_band_chf} />
                    <Field label="Weekly Hours" value={`${data.weekly_hours}h`} />
                    <Field label="Since" value={data.employment_start_year.toString()} />
                    
                    <div className="col-span-2">
                      <EditableField 
                        label="Daily Commute (km)" 
                        value={data.commute_km_daily} 
                        onChange={(v) => updateData("commute_km_daily", v)}
                        isMissing={missingFields.includes("commute_km_daily")}
                        type="number"
                      />
                    </div>
                  </div>
                </div>

                {/* Housing Section */}
                <div className="bg-[var(--color-bank-surface)] border border-[var(--color-bank-border)] rounded-xl overflow-hidden shadow-sm">
                  <div className="px-6 py-4 border-b border-[var(--color-bank-border)] bg-[var(--color-bank-bg)] flex items-center">
                    <Home className="w-4 h-4 mr-3 text-[var(--color-bank-text-muted)]" />
                    <h3 className="font-medium">Housing</h3>
                  </div>
                  <div className="p-6 grid grid-cols-2 gap-x-8 gap-y-6">
                    <Field label="Status" value={data.housing_status} />
                    <Field label="Monthly Rent" value={`CHF ${data.rent_chf_monthly}`} />
                    <Field label="Since" value={data.rental_start_year.toString()} />
                    <Field label="Ref. Rate Tracked" value={data.lease_reference_rate_tracked ? "Yes" : "No"} />
                    
                    <div className="col-span-2">
                      <EditableSelect 
                        label="Canton of Residence" 
                        value={data.canton} 
                        onChange={(v) => updateData("canton", v)}
                        options={CANTONS.map(c => ({value: c, label: c}))}
                        isMissing={missingFields.includes("canton")}
                      />
                    </div>
                  </div>
                </div>

                {/* Family Section */}
                <div className="bg-[var(--color-bank-surface)] border border-[var(--color-bank-border)] rounded-xl overflow-hidden shadow-sm opacity-70 hover:opacity-100 transition-opacity">
                  <div className="px-6 py-4 border-b border-[var(--color-bank-border)] bg-[var(--color-bank-bg)] flex items-center">
                    <Users className="w-4 h-4 mr-3 text-[var(--color-bank-text-muted)]" />
                    <h3 className="font-medium">Household &amp; Family</h3>
                  </div>
                  <div className="p-6 grid grid-cols-2 gap-x-8 gap-y-6">
                    <Field label="Marital Status" value={data.marital_status} />
                    <Field label="Household Size" value={data.household_size.toString()} />
                    <Field label="Children" value={data.children_count.toString()} />
                    <Field label="Childcare Cost" value={`CHF ${data.childcare_cost_chf_yearly}/yr`} />
                  </div>
                </div>

                {/* Savings & Pension Section -- not on documents, requires confirmation */}
                <div className="bg-[var(--color-bank-surface)] border border-[var(--color-bank-border)] rounded-xl overflow-hidden shadow-sm">
                  <div className="px-6 py-4 border-b border-[var(--color-bank-border)] bg-[var(--color-bank-bg)] flex items-center">
                    <Wallet className="w-4 h-4 mr-3 text-[var(--color-bank-text-muted)]" />
                    <h3 className="font-medium">Savings &amp; Pension</h3>
                    <span className="ml-auto text-[10px] font-medium uppercase tracking-wider text-[var(--color-bank-text-muted)] bg-[var(--color-bank-bg)] border border-[var(--color-bank-border)] px-2 py-0.5 rounded">Confirm</span>
                  </div>
                  <div className="p-6 space-y-5">
                    <label className="flex items-start space-x-3 cursor-pointer p-3 -m-3 rounded-lg hover:bg-[var(--color-bank-bg)] transition-colors">
                      <input
                        type="checkbox"
                        checked={data.has_third_pillar}
                        onChange={(e) => updateData("has_third_pillar", e.target.checked)}
                        className="mt-1 h-4 w-4 rounded border-[var(--color-bank-border)] text-[var(--color-brand)] focus:ring-[var(--color-brand)]"
                      />
                      <div className="flex-1">
                        <div className="text-sm font-medium text-[var(--color-bank-text)]">I contribute to a 3rd Pillar (Pillar 3a)</div>
                        <div className="text-xs text-[var(--color-bank-text-muted)] mt-0.5">Tax-deductible private retirement savings — not present on the uploaded documents.</div>
                      </div>
                    </label>
                    {data.has_third_pillar && (
                      <div className="pl-7">
                        <EditableField
                          label="Pillar 3a Contributions This Year (CHF)"
                          value={data.third_pillar_chf_this_year}
                          onChange={(v) => updateData("third_pillar_chf_this_year", v)}
                          isMissing={false}
                          type="number"
                        />
                      </div>
                    )}
                  </div>
                </div>

              </div>
            </div>

            {/* Right Column: Context & Actions */}
            <div className="col-span-4 relative">
              <div className="sticky top-28 space-y-6">
                
                {/* Document Sources */}
                <div className="bg-[var(--color-bank-surface)] border border-[var(--color-bank-border)] rounded-xl p-5 shadow-sm">
                  <h4 className="text-xs font-semibold text-[var(--color-bank-text-muted)] uppercase tracking-wider mb-4">Source Documents</h4>
                  <div className="space-y-3">
                    {(files.length > 0 ? files : [{name: "Lohnausweis_2023.pdf", type: "pdf"}, {name: "Mietvertrag_Signed.pdf", type: "pdf"}]).map((f, i) => (
                      <div key={i} className="flex items-center text-sm p-2 rounded-lg bg-[var(--color-bank-bg)] border border-[var(--color-bank-border)]">
                        <FileText className="w-4 h-4 mr-3 text-[var(--color-brand)]" />
                        <span className="truncate flex-1">{f.name}</span>
                        <CheckCircle2 className="w-4 h-4 text-green-500 ml-2 flex-shrink-0" />
                      </div>
                    ))}
                  </div>
                </div>

                {/* Status & CTA */}
                <div className="bg-[var(--color-bank-surface)] border border-[var(--color-bank-border)] rounded-xl p-6 shadow-sm text-center">
                  <div className="w-16 h-16 mx-auto bg-[var(--color-bank-bg)] rounded-full border border-[var(--color-bank-border)] flex items-center justify-center mb-4">
                    {missingFields.length > 0 ? (
                      <span className="text-xl font-serif text-[var(--color-brand)]">{missingFields.length}</span>
                    ) : (
                      <CheckCircle2 className="w-8 h-8 text-[var(--color-brand)]" />
                    )}
                  </div>
                  <h3 className="font-serif text-xl text-[var(--color-bank-text)] mb-2">
                    {missingFields.length > 0 ? "Missing Information" : "Ready to Scan"}
                  </h3>
                  <p className="text-sm text-[var(--color-bank-text-muted)] mb-6">
                    {missingFields.length > 0 
                      ? `Please complete the ${missingFields.length} remaining field${missingFields.length > 1 ? 's' : ''} highlighted in the form.` 
                      : "Your profile is complete. We are ready to analyze your rights and deductions."}
                  </p>
                  <button 
                    onClick={runScan}
                    disabled={missingFields.length > 0 || scanning}
                    className="w-full py-3.5 px-4 bg-[var(--color-brand)] hover:bg-[var(--color-brand-hover)] text-white rounded-lg font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center"
                  >
                    {scanning ? (
                      <><RefreshCw className="w-4 h-4 mr-2 animate-spin" /> Analyzing...</>
                    ) : (
                      <><Wallet className="w-4 h-4 mr-2" /> Run Rights Scan</>
                    )}
                  </button>
                </div>

              </div>
            </div>

          </div>
        )}
      </main>
    </div>
  );
}

// Subcomponents for the Review Step

function Field({ label, value }: { label: string, value: string | React.ReactNode }) {
  return (
    <div>
      <div className="text-xs font-medium text-[var(--color-bank-text-muted)] mb-1 uppercase tracking-wide">{label}</div>
      <div className="text-sm font-medium text-[var(--color-bank-text)] flex items-center">
        {value}
        <span className="ml-2 inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium bg-[var(--color-bank-bg)] text-[var(--color-bank-text-muted)] border border-[var(--color-bank-border)]">Extracted</span>
      </div>
    </div>
  );
}

function EditableField({ label, value, onChange, isMissing, type="text" }: { label: string, value: any, onChange: (v: string) => void, isMissing: boolean, type?: string }) {
  return (
    <div className={`p-4 rounded-lg border transition-colors ${isMissing ? 'bg-amber-50 border-amber-200' : 'bg-white border-[var(--color-bank-border)]'}`}>
      <div className="flex items-center justify-between mb-2">
        <label className="text-xs font-semibold text-[var(--color-bank-text-muted)] uppercase tracking-wide flex items-center">
          {label}
          {isMissing && <span className="ml-2 text-amber-600 text-[10px] bg-amber-100 px-1.5 py-0.5 rounded">Required</span>}
        </label>
      </div>
      <input 
        type={type}
        value={value || ""}
        onChange={(e) => onChange(e.target.value)}
        className="w-full bg-transparent border-b-2 border-[var(--color-bank-border)] focus:border-[var(--color-brand)] outline-none py-1.5 text-sm font-medium transition-colors"
        placeholder={`Enter ${label.toLowerCase()}`}
      />
    </div>
  );
}

function EditableSelect({ label, value, onChange, options, isMissing }: { label: string, value: string, onChange: (v: string) => void, options: {label: string, value: string}[], isMissing: boolean }) {
  return (
    <div className={`p-4 rounded-lg border transition-colors ${isMissing ? 'bg-amber-50 border-amber-200' : 'bg-white border-[var(--color-bank-border)]'}`}>
      <div className="flex items-center justify-between mb-2">
        <label className="text-xs font-semibold text-[var(--color-bank-text-muted)] uppercase tracking-wide flex items-center">
          {label}
          {isMissing && <span className="ml-2 text-amber-600 text-[10px] bg-amber-100 px-1.5 py-0.5 rounded">Required</span>}
        </label>
      </div>
      <select 
        value={value || ""}
        onChange={(e) => onChange(e.target.value)}
        className="w-full bg-transparent border-b-2 border-[var(--color-bank-border)] focus:border-[var(--color-brand)] outline-none py-1.5 text-sm font-medium transition-colors cursor-pointer"
      >
        <option value="" disabled>Select {label.toLowerCase()}</option>
        {options.map(o => (
          <option key={o.value} value={o.value}>{o.label}</option>
        ))}
      </select>
    </div>
  );
}
